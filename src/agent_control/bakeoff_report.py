"""V7 T05 — bake-off report (longitudinal compare + negative-transfer + production gates)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_control.bakeoff_memory import BakeoffMemoryFacade
from agent_control.bakeoff_metrics import METRIC_FIELDS
from agent_control.bakeoff_profiles import PROFILE_IDS, run_all_profiles_against_bundle
from agent_control.security.injection_scanner import scanner_cannot_grant_authority
from agent_shared.models.injection_assessment import InjectionAssessment

REPORT_SCHEMA = "bakeoff_report.v1"
BASELINE_PROFILE = "A"


class BakeoffReportError(ValueError):
    """Invalid bake-off report inputs or production-gate failure."""


def assert_production_gates(run_doc: dict[str, Any]) -> dict[str, Any]:
    """Fail closed if a bake-off run flips production-danger flags."""
    pid = run_doc.get("profile_id", "?")
    if run_doc.get("unbounded_recursion") is not False:
        raise BakeoffReportError(f"profile {pid}: unbounded_recursion must remain OFF")
    if run_doc.get("injection_shadow_is_authority") is not False:
        raise BakeoffReportError(f"profile {pid}: shadow injection must not be authority")
    if run_doc.get("production_memory_touched") is not False:
        raise BakeoffReportError(f"profile {pid}: production memory must not be touched")
    isolation = run_doc.get("memory_isolation") or {}
    if isolation.get("production_memory_touched") is True:
        raise BakeoffReportError(f"profile {pid}: isolation facade marked production touched")
    ns = str(run_doc.get("memory_namespace") or "")
    if not ns.startswith("bakeoff/"):
        raise BakeoffReportError(f"profile {pid}: memory_namespace must be bakeoff/*, got {ns!r}")
    return {
        "unbounded_recursion": False,
        "injection_shadow_is_authority": False,
        "production_memory_touched": False,
        "shadow_scanner_cannot_grant_authority": True,
        "memory_namespace_prefix_ok": True,
    }


def _metrics_slice(run_doc: dict[str, Any]) -> dict[str, Any]:
    metrics = run_doc.get("metrics") or {}
    return {k: metrics.get(k) for k in METRIC_FIELDS}


def _row_for_run(run_doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "profile_id": run_doc.get("profile_id"),
        "profile_name": run_doc.get("profile_name"),
        "controller_backend": run_doc.get("controller_backend"),
        "context_strategy": run_doc.get("context_strategy"),
        "recursive_context_enabled": run_doc.get("recursive_context_enabled"),
        "experimental": bool(run_doc.get("experimental")),
        "bounds": run_doc.get("bounds") or {},
        "memory_namespace": run_doc.get("memory_namespace"),
        "mode": run_doc.get("mode"),
        "metrics": _metrics_slice(run_doc),
        "source_eval_bundle_sha256": run_doc.get("source_eval_bundle_sha256"),
    }


def _delta_vs_baseline(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    b = baseline.get("metrics") or {}
    c = candidate.get("metrics") or {}
    success_delta = int(bool(c.get("ct102_verified_success"))) - int(
        bool(b.get("ct102_verified_success"))
    )
    return {
        "ct102_verified_success_delta": success_delta,
        "repair_iterations_delta": int(c.get("repair_iterations") or 0)
        - int(b.get("repair_iterations") or 0),
        "fallback_count_delta": int(c.get("fallback_count") or 0)
        - int(b.get("fallback_count") or 0),
        "policy_violations_delta": int(c.get("policy_violations") or 0)
        - int(b.get("policy_violations") or 0),
        "tokens_total_delta": (
            int(c.get("tokens_input") or 0) + int(c.get("tokens_output") or 0)
        )
        - (int(b.get("tokens_input") or 0) + int(b.get("tokens_output") or 0)),
        "cost_usd_delta": round(
            float(c.get("cost_usd") or 0.0) - float(b.get("cost_usd") or 0.0), 6
        ),
        "wall_seconds_delta": round(
            float(c.get("wall_seconds") or 0.0) - float(b.get("wall_seconds") or 0.0), 3
        ),
    }


def _is_negative_transfer(delta: dict[str, Any]) -> bool:
    """Worse verification, or no success gain with more repair/cost/violations."""
    if delta["ct102_verified_success_delta"] < 0:
        return True
    if delta["ct102_verified_success_delta"] == 0 and (
        delta["repair_iterations_delta"] > 0
        or delta["policy_violations_delta"] > 0
        or delta["cost_usd_delta"] > 0
        or delta["wall_seconds_delta"] > 0
        or delta["fallback_count_delta"] > 0
    ):
        return True
    return False


def build_negative_transfer_notes(
    rows: list[dict[str, Any]],
    *,
    dry_run_parity: bool,
) -> list[dict[str, Any]]:
    """Structured notes: metric regressions vs A plus promotion / isolation caveats."""
    by_id = {str(r["profile_id"]): r for r in rows}
    baseline = by_id.get(BASELINE_PROFILE)
    notes: list[dict[str, Any]] = []

    if dry_run_parity:
        notes.append(
            {
                "kind": "dry_run_parity",
                "severity": True,
                "summary": (
                    "Dry-run bake-off shares source-bundle metrics across A–D; "
                    "longitudinal deltas are zero until live controller ablation runs."
                ),
                "promotion_blocked": True,
            }
        )

    if baseline is None:
        notes.append(
            {
                "kind": "missing_baseline",
                "severity": True,
                "summary": f"Baseline profile {BASELINE_PROFILE} missing; cannot score transfer.",
                "promotion_blocked": True,
            }
        )
        return notes

    for pid in PROFILE_IDS:
        if pid == BASELINE_PROFILE:
            continue
        row = by_id.get(pid)
        if row is None:
            continue
        delta = _delta_vs_baseline(baseline, row)
        negative = _is_negative_transfer(delta) and not dry_run_parity
        notes.append(
            {
                "kind": "vs_baseline",
                "profile_id": pid,
                "baseline_profile_id": BASELINE_PROFILE,
                "delta": delta,
                "negative_transfer": negative,
                "severity": negative or bool(row.get("experimental")),
                "summary": (
                    f"Profile {pid} vs {BASELINE_PROFILE}: "
                    + (
                        "metric regression / no-gain cost — do not promote"
                        if negative
                        else (
                            "experimental backend; require live CT102 win before mandatory"
                            if row.get("experimental")
                            else "no negative-transfer signal on recorded metrics"
                        )
                    )
                ),
                "promotion_blocked": negative or bool(row.get("experimental")) or dry_run_parity,
            }
        )

    notes.append(
        {
            "kind": "memory_isolation",
            "severity": False,
            "summary": (
                "Cross-profile writebacks stay under bakeoff/* namespaces; "
                "isolation prevents memory-bleed negative transfer into production."
            ),
            "promotion_blocked": False,
        }
    )
    notes.append(
        {
            "kind": "promotion_rule",
            "severity": True,
            "summary": (
                "Do not make a non-baseline controller mandatory unless it improves "
                "CT102 verified success or cost/latency without unacceptable negative transfer."
            ),
            "promotion_blocked": True,
        }
    )
    return notes


def _shadow_authority_invariant_ok() -> bool:
    """Confirm shadow InjectionAssessment cannot grant authority (library invariant)."""
    assessment = InjectionAssessment(
        mode="shadow",
        authority_granted=False,
        assessed_at=datetime.now(timezone.utc).isoformat(),
    )
    return scanner_cannot_grant_authority(assessment)


def build_bakeoff_report(
    run_docs: list[dict[str, Any]],
    *,
    report_id: str | None = None,
) -> dict[str, Any]:
    """Assemble bakeoff_report.v1 from profile run documents."""
    if len(run_docs) != len(PROFILE_IDS):
        raise BakeoffReportError(
            f"expected {len(PROFILE_IDS)} profile runs, got {len(run_docs)}"
        )
    ids = [str(d.get("profile_id")) for d in run_docs]
    if set(ids) != set(PROFILE_IDS):
        raise BakeoffReportError(f"profile ids must be A–D, got {ids}")

    gate_blocks: dict[str, Any] = {}
    for doc in run_docs:
        gate_blocks[str(doc.get("profile_id"))] = assert_production_gates(doc)

    if not _shadow_authority_invariant_ok():
        raise BakeoffReportError("shadow injection scanner must not grant authority")

    digests = {d.get("source_eval_bundle_sha256") for d in run_docs}
    if len(digests) != 1:
        raise BakeoffReportError("longitudinal compare requires one shared eval_bundle digest")

    rows = [_row_for_run(d) for d in sorted(run_docs, key=lambda x: str(x.get("profile_id")))]
    metric_sets = [tuple(sorted((r["metrics"] or {}).items())) for r in rows]
    dry_run_parity = len(set(metric_sets)) == 1

    longitudinal: list[dict[str, Any]] = []
    baseline = next(r for r in rows if r["profile_id"] == BASELINE_PROFILE)
    for row in rows:
        entry = dict(row)
        if row["profile_id"] == BASELINE_PROFILE:
            entry["delta_vs_baseline"] = None
        else:
            entry["delta_vs_baseline"] = _delta_vs_baseline(baseline, row)
        longitudinal.append(entry)

    notes = build_negative_transfer_notes(rows, dry_run_parity=dry_run_parity)
    any_negative = any(n.get("negative_transfer") for n in notes if "negative_transfer" in n)
    any_prod_touch = any(d.get("production_memory_touched") for d in run_docs)

    digest = next(iter(digests))
    return {
        "schema_version": REPORT_SCHEMA,
        "report_id": report_id or f"bakeoff-{str(digest)[:12]}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_eval_bundle_sha256": digest,
        "profiles_compared": list(PROFILE_IDS),
        "baseline_profile_id": BASELINE_PROFILE,
        "mode": run_docs[0].get("mode") or "dry_run",
        "dry_run_metric_parity": dry_run_parity,
        "longitudinal": longitudinal,
        "negative_transfer_notes": notes,
        "negative_transfer_detected": bool(any_negative),
        "production_gates": {
            "unbounded_recursion": False,
            "injection_shadow_is_authority": False,
            "production_memory_touched": False,
            "shadow_scanner_cannot_grant_authority": True,
            "per_profile": gate_blocks,
            "all_passed": True,
        },
        "production_memory_touched": bool(any_prod_touch),
        "recommendation": (
            "Keep baseline A as default; treat B/C as bounded optional ablation; "
            "keep D experimental. Do not enable unbounded recursion or shadow authority "
            "in production. Live controller runs required before promoting any profile."
            if dry_run_parity
            else (
                "Negative transfer detected — do not promote regressing profiles."
                if any_negative
                else "Recorded metrics show no negative transfer vs A; still require live CT102 proof before mandatory promotion."
            )
        ),
        "field_contract": {
            "metrics": list(METRIC_FIELDS),
            "profiles": list(PROFILE_IDS),
        },
    }


def write_bakeoff_report(report: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    digest = str(report.get("source_eval_bundle_sha256") or "unknown")[:12]
    path = output_dir / f"bakeoff-report-{digest}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return path


def emit_bakeoff_report_for_bundle(
    bundle_path: Path,
    *,
    output_dir: Path,
    config_path: Path | None = None,
    memory: BakeoffMemoryFacade | None = None,
) -> tuple[dict[str, Any], Path, list[tuple[dict[str, Any], Path]]]:
    """Run A–D, assert gates, write bakeoff_report.v1. Never mutates production memory."""
    facade = memory or BakeoffMemoryFacade()
    results = run_all_profiles_against_bundle(
        bundle_path,
        output_dir=output_dir / "runs",
        config_path=config_path,
        memory=facade,
    )
    if facade.production_memory_touched:
        raise BakeoffReportError("bake-off report must not touch production memory")
    run_docs = [doc for doc, _ in results]
    report = build_bakeoff_report(run_docs)
    report_path = write_bakeoff_report(report, output_dir)
    return report, report_path, results
