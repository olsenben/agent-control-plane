"""Quality-triggered model retry and fallback (Slice 6D.1)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

from agent_shared.constants import TERMINAL_STATUS_FAILED_QUALITY_GATE
from agent_shared.models.fix import FixResult
from agent_shared.models.plan import PlanResult
from agent_shared.models.runs import RLMResult
from agent_workers.formatters.plan_quality_failed import render_plan_quality_failed
from agent_workers.rlm.budget import fit_summary_for_comment
from agent_shared.constants import GITEA_COMMENT_SUMMARY_PROMPT_BUDGET_CHARS
from agent_workers.rlm.model_routing import (
    WorkerResolvedEndpoint,
    resolve_rlm_external_endpoint,
    resolve_rlm_gpu_endpoint,
    to_control_plane_endpoint,
)
from agent_workers.rlm.output_quality import (
    QualityVerdict,
    evaluate_fix_output_quality,
    evaluate_plan_output_quality,
    write_model_output_excerpt,
    write_quality_gate_result,
)

Kind = Literal["plan", "fix"]
_STRICT_SUFFIX = (
    "\n\nReturn actionable output with at least one step referencing concrete repo file paths in files[]."
)
_FIX_STRICT_SUFFIX = (
    "\n\nReturn at least one file change in changes[] with path and content for each allowed file edit."
)


@dataclass
class QualityAttemptResult:
    ok: bool
    raw_response: str
    parsed: PlanResult | FixResult | None
    summary: str | None
    warnings: list[str]
    verdict: QualityVerdict | None = None


def _attempts_for_kind(kind: Kind) -> list[tuple[str, WorkerResolvedEndpoint | None, str]]:
    gpu = resolve_rlm_gpu_endpoint()
    external = resolve_rlm_external_endpoint()
    attempts: list[tuple[str, WorkerResolvedEndpoint | None, str]] = [
        ("gpu_initial", gpu, ""),
        ("gpu_retry", gpu, _STRICT_SUFFIX if kind == "plan" else _FIX_STRICT_SUFFIX),
    ]
    if external is not None:
        attempts.append(("external_fallback", external, _STRICT_SUFFIX if kind == "plan" else _FIX_STRICT_SUFFIX))
    return attempts


def build_quality_failed_result(
    *,
    job: dict[str, Any],
    kind: Kind,
    reasons: list[str],
    fallback_attempted: bool,
    engine_name: str,
) -> RLMResult:
    run_id = str(job["run_id"])
    if kind == "plan":
        summary = render_plan_quality_failed(
            run_id=run_id,
            reasons=reasons,
            fallback_attempted=fallback_attempted,
        )
    else:
        from agent_workers.formatters.fix_comment import render_fix_quality_failed

        summary = render_fix_quality_failed(run_id=run_id, reasons=reasons, fallback_attempted=fallback_attempted)
    summary = fit_summary_for_comment(summary, GITEA_COMMENT_SUMMARY_PROMPT_BUDGET_CHARS)
    return RLMResult(
        run_id=run_id,
        session_id=job["session_id"],
        project=job["project"],
        flow=job["flow"],
        agent=job["agent"],
        risk_class=job["risk_class"],
        workflow_definition=job["workflow_definition"],
        flow_config_id=job["flow_config_id"],
        flow_version=job["flow_version"],
        status="failed",
        terminal_status=TERMINAL_STATUS_FAILED_QUALITY_GATE,
        summary=summary,
        engine=engine_name,
        trace_path="rlm_trace.jsonl",
        context_receipt_path="context_receipt.json",
        warnings=[],
    )


def run_quality_gated_attempts(
    *,
    kind: Kind,
    job: dict[str, Any],
    artifact_dir: str | None,
    engine_name: str,
    call_model: Callable[[WorkerResolvedEndpoint, str], str],
    parse_and_finalize: Callable[[str, Any], tuple[str, PlanResult | FixResult, list[str]]],
) -> tuple[RLMResult | None, QualityAttemptResult | None]:
    """Run GPU retry + optional external fallback. Returns failed RLMResult or None with success attempt."""
    all_reasons: list[str] = []
    fallback_attempted = False
    artifact_path = Path(artifact_dir) if artifact_dir else None

    for attempt_idx, (label, endpoint, suffix) in enumerate(_attempts_for_kind(kind), start=1):
        if endpoint is None or not endpoint.base_url:
            continue
        if label == "external_fallback":
            fallback_attempted = True
        raw = call_model(endpoint, suffix)
        if artifact_path is not None:
            write_model_output_excerpt(artifact_path, raw, attempt=attempt_idx)
        cp_endpoint = to_control_plane_endpoint(endpoint)
        try:
            summary, parsed, warnings = parse_and_finalize(raw, cp_endpoint)
        except Exception:
            continue
        if kind == "plan":
            assert isinstance(parsed, PlanResult)
            verdict = evaluate_plan_output_quality(parsed)
        else:
            assert isinstance(parsed, FixResult)
            verdict = evaluate_fix_output_quality(parsed)
        if verdict.passed:
            return None, QualityAttemptResult(
                ok=True,
                raw_response=raw,
                parsed=parsed,
                summary=summary,
                warnings=warnings,
                verdict=verdict,
            )
        all_reasons = list(verdict.reasons)

    if artifact_path is not None:
        write_quality_gate_result(
            artifact_path,
            QualityVerdict(passed=False, reasons=all_reasons or ["Output failed quality gate."]),
        )
    failed = build_quality_failed_result(
        job=job,
        kind=kind,
        reasons=all_reasons or ["Output failed quality gate after retries."],
        fallback_attempted=fallback_attempted,
        engine_name=engine_name,
    )
    return failed, None
