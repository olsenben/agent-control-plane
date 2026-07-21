"""V7 T03 — bake-off metrics from eval_bundle timeline / stages."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_control.inspect_adapter import load_eval_bundle
from agent_shared.models.eval_bundle import EvalBundle

# Documented metric field contract (bakeoff_metrics.v1).
METRIC_FIELDS = (
    "ct102_verified_success",
    "repair_iterations",
    "fallback_count",
    "policy_violations",
    "tokens_input",
    "tokens_output",
    "cost_usd",
    "wall_seconds",
)


def _payload(event: dict[str, Any]) -> dict[str, Any]:
    p = event.get("payload")
    return p if isinstance(p, dict) else {}


def _event_type(event: dict[str, Any]) -> str:
    return str(event.get("type") or "")


def _kind(event: dict[str, Any]) -> str:
    return str(_payload(event).get("kind") or "").lower()


def _summary(event: dict[str, Any]) -> str:
    return str(_payload(event).get("summary") or "").lower()


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def extract_metrics_from_bundle(bundle: EvalBundle) -> dict[str, Any]:
    """Derive bakeoff_metrics.v1 fields from a verified eval bundle (read-only)."""
    timeline = bundle.timeline or []
    stages = bundle.stages or []

    repair_iterations = 0
    fallback_count = 0
    policy_violations = 0
    tokens_input = 0
    tokens_output = 0
    cost_usd = 0.0
    wall_seconds = 0.0
    ct102_signals: list[str] = []

    for event in timeline:
        et = _event_type(event)
        kind = _kind(event)
        summary = _summary(event)
        payload = _payload(event)

        # Repair / CI repair loops
        if "repair" in et.lower() or kind in {"ci_repair", "repair", "sandboxed_repair"}:
            repair_iterations += 1
        if "repair" in summary and "iter" in summary:
            repair_iterations += 1

        # Gateway / model fallback
        if kind in {"fallback", "model_fallback", "model_fallback_selected"} or "fallback" in summary:
            fallback_count += 1
        if payload.get("provider") == "fallback" or payload.get("used_fallback") is True:
            fallback_count += 1

        # Policy / authorization denials
        if kind in {
            "policy_denied",
            "authorization_denied",
            "budget_exhausted",
            "blocked",
            "memory_governance_denied",
            "sandbox_denied",
            "patch_rejected",
        }:
            policy_violations += 1
        decision = str(payload.get("policy_decision") or payload.get("decision") or "").lower()
        if decision in {"denied", "blocked", "reject", "rejected"}:
            policy_violations += 1

        # Token / cost / time if recorded on events
        tokens_input += _as_int(payload.get("tokens_input") or payload.get("input_tokens"))
        tokens_output += _as_int(payload.get("tokens_output") or payload.get("output_tokens"))
        tc = payload.get("token_counts")
        if isinstance(tc, dict):
            tokens_input += _as_int(tc.get("input") or tc.get("prompt_tokens"))
            tokens_output += _as_int(tc.get("output") or tc.get("completion_tokens"))
        cost_usd += _as_float(payload.get("cost_usd") or payload.get("cost"))
        wall_seconds += _as_float(
            payload.get("wall_seconds") or payload.get("duration_seconds") or payload.get("elapsed_s")
        )

        # CT102 verification signals
        if kind in {
            "ci_passed",
            "ct102_verified",
            "verification_passed",
            "ci_verdict_accepted",
        }:
            ct102_signals.append(kind)
        if "ci" in et.lower() and "pass" in summary:
            ct102_signals.append("ci_pass_summary")
        if "ct102" in summary and "verif" in summary:
            ct102_signals.append("ct102_summary")
        claim = str(payload.get("claim") or payload.get("verification_claim") or "").lower()
        if claim in {"fixed_verified", "ci_regression_passed", "verified"}:
            ct102_signals.append(claim)

    # Stages: look for verification / waiting_for_ci terminal success
    stage_verified = False
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        name = str(stage.get("name") or "").lower()
        status = str(stage.get("status") or "").lower()
        if name in {"verification", "ci", "waiting_for_ci", "publish"} and status in {
            "ok",
            "passed",
            "success",
            "complete",
            "completed",
        }:
            stage_verified = True
            ct102_signals.append(f"stage:{name}:{status}")

    ct102_verified_success = bool(ct102_signals) or stage_verified

    return {
        "schema_version": "bakeoff_metrics.v1",
        "ct102_verified_success": ct102_verified_success,
        "repair_iterations": repair_iterations,
        "fallback_count": fallback_count,
        "policy_violations": policy_violations,
        "tokens_input": tokens_input,
        "tokens_output": tokens_output,
        "cost_usd": round(cost_usd, 6),
        "wall_seconds": round(wall_seconds, 3),
        "evidence": {
            "ct102_signals": ct102_signals[:20],
            "event_count": len(timeline),
            "stage_count": len(stages),
            "source_eval_bundle_sha256": bundle.eval_bundle_sha256,
            "memory_namespace": bundle.memory_namespace,
            "production_memory_touched": False,
        },
        "field_contract": list(METRIC_FIELDS),
        "extracted_at": datetime.now(timezone.utc).isoformat(),
    }


def build_metrics_for_bundle_file(bundle_path: Path) -> dict[str, Any]:
    """Load+verify bundle then extract metrics (fail-closed on SHA)."""
    bundle = load_eval_bundle(bundle_path)
    return extract_metrics_from_bundle(bundle)


def write_metrics(
    metrics: dict[str, Any],
    output_dir: Path,
    *,
    profile_id: str | None = None,
) -> Path:
    """Write bakeoff_metrics.v1 JSON; never touches production memory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    digest = (metrics.get("evidence") or {}).get("source_eval_bundle_sha256", "unknown")[:12]
    prefix = f"metrics-{profile_id}-" if profile_id else "metrics-"
    path = output_dir / f"{prefix}{digest}.json"
    path.write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")
    return path


def attach_metrics_to_bakeoff_run(
    run_doc: dict[str, Any],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    """Return a copy of bakeoff_run with metrics embedded."""
    out = dict(run_doc)
    out["metrics"] = metrics
    out["metrics_schema"] = "bakeoff_metrics.v1"
    return out
