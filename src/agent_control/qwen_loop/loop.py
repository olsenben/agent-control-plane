"""Bounded recursive Qwen loop — CI-grounded retry decision (T08)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from agent_control.qwen_loop.config import (
    budget_from_config,
    load_qwen_loop_config,
    loop_enabled,
    require_evidence_for_retry,
)
from agent_control.qwen_loop.evidence import context_has_usable_evidence, select_evidence_context
from agent_shared.models.ci import FailureEvidenceManifest
from agent_shared.models.memory_preflight import MemoryPreflight
from agent_shared.models.qwen_loop import (
    SCHEMA_VERSION,
    QwenLoopAttemptRecord,
    QwenLoopBudget,
    QwenLoopResult,
    StopReason,
)
from agent_shared.models.recursive_context import RecursiveContextResult


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def evaluate_ci_grounded_retry(
    *,
    session_id: str,
    run_id: str,
    repo: str,
    ci_verdict: str,
    completed_attempts: int = 0,
    evidence: FailureEvidenceManifest | None = None,
    recursive_context: RecursiveContextResult | None = None,
    preflight: MemoryPreflight | None = None,
    prior: QwenLoopResult | None = None,
    budget: QwenLoopBudget | None = None,
    config: dict[str, Any] | None = None,
    force_enabled: bool | None = None,
) -> QwenLoopResult:
    """Decide whether another Qwen attempt is allowed after a CI outcome.

    Invariants:
    - ``max_attempts`` is always finite and >= 1 when enabled
    - ``bounded`` / ``unbounded_forbidden`` are always True
    - action=retry only when ci_verdict=failing AND attempt < max AND evidence ok
    - Never schedules 6F.2 repair; callers must not treat retry as allowlist enablement
    """
    cfg = config if config is not None else load_qwen_loop_config()
    budget = budget or budget_from_config(cfg)
    enabled = loop_enabled(cfg) if force_enabled is None else bool(force_enabled)
    max_attempts = max(1, int(budget.max_ci_repair_iterations))
    created = prior.created_at if prior and prior.created_at else _now()
    updated = _now()

    prior_records = list(prior.prior_attempts) if prior else []
    if prior is not None and prior.attempt > 0:
        prior_records = list(prior.prior_attempts)
        # Include the immediately previous decision if not already listed.
        last = QwenLoopAttemptRecord(
            attempt=prior.attempt,
            ci_verdict=prior.ci_verdict,
            action=prior.action,
            stop_reason=prior.stop_reason,
            evidence_ref_count=len(prior.selected_context.evidence_refs),
        )
        if not prior_records or prior_records[-1].attempt != last.attempt:
            prior_records.append(last)

    attempt = max(0, int(completed_attempts)) + 1
    selected = select_evidence_context(
        evidence=evidence,
        recursive_context=recursive_context,
        preflight=preflight,
        budget=budget,
    )
    notes: list[str] = [
        "does_not_enable_6f2_repair_allowlist",
        "ci_grounded_external_feedback_required",
    ]

    def _result(
        *,
        action: str,
        stop_reason: StopReason,
        extra_notes: list[str] | None = None,
    ) -> QwenLoopResult:
        return QwenLoopResult(
            schema_version=SCHEMA_VERSION,
            schema_name=SCHEMA_VERSION,
            session_id=session_id,
            run_id=run_id,
            repo=repo,
            enabled=enabled,
            attempt=attempt,
            max_attempts=max_attempts,
            ci_verdict=ci_verdict,
            action=action,  # type: ignore[arg-type]
            stop_reason=stop_reason,
            selected_context=selected,
            prior_attempts=prior_records[-20:],
            bounded=True,
            unbounded_forbidden=True,
            created_at=created,
            updated_at=updated,
            notes=notes + (extra_notes or []),
        )

    if not enabled:
        return _result(action="stop", stop_reason="disabled", extra_notes=["loop_disabled"])

    if ci_verdict == "verified":
        return _result(action="stop", stop_reason="verification_passed")

    if ci_verdict != "failing":
        return _result(action="stop", stop_reason="not_ci_failing")

    # Hard bound: completed_attempts already consumed the budget.
    if completed_attempts >= max_attempts or attempt > max_attempts:
        return _result(
            action="stop",
            stop_reason="budget_exhausted",
            extra_notes=[f"max_ci_repair_iterations={max_attempts}"],
        )

    if require_evidence_for_retry(cfg) and not context_has_usable_evidence(selected):
        return _result(
            action="stop",
            stop_reason="insufficient_evidence",
            extra_notes=["require_evidence_for_retry"],
        )

    if recursive_context is not None and recursive_context.stop_reason == "contradictory_evidence":
        return _result(action="stop", stop_reason="contradictory_evidence")

    if recursive_context is not None and recursive_context.stop_reason == "human_required":
        return _result(action="stop", stop_reason="human_required")

    return _result(
        action="retry",
        stop_reason="sufficient_evidence",
        extra_notes=["evidence_selected_for_next_qwen_pass"],
    )


def assert_loop_terminates(
    *,
    max_attempts: int,
    start_completed: int = 0,
    ci_verdict: str = "failing",
    has_evidence: bool = True,
) -> list[QwenLoopResult]:
    """Simulate successive CI-fail decisions; always terminates within max_attempts+1.

    Used by tests to prove the controller cannot run unbounded.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    budget = QwenLoopBudget(max_ci_repair_iterations=max_attempts)
    evidence = None
    if has_evidence:
        evidence = FailureEvidenceManifest(
            evidence_observation_id="obs-sim",
            status="collected",
            fix_run_id="run-sim",
            repository="ai-sdlc-lab/demo-app",
            expected_head_commit_sha="sha",
            workflow_run_id="42",
            failure_class="lint_failure",
            has_terminal_failed_job=True,
            collected_at=_now(),
        )
    results: list[QwenLoopResult] = []
    prior: QwenLoopResult | None = None
    completed = start_completed
    # Safety ceiling: never more than max_attempts + 2 iterations in the simulator.
    for _ in range(max_attempts + 2):
        result = evaluate_ci_grounded_retry(
            session_id="sess-sim",
            run_id="run-sim",
            repo="ai-sdlc-lab/demo-app",
            ci_verdict=ci_verdict,
            completed_attempts=completed,
            evidence=evidence,
            prior=prior,
            budget=budget,
            force_enabled=True,
        )
        results.append(result)
        prior = result
        if result.action == "stop":
            break
        completed += 1
    else:
        raise RuntimeError("qwen loop simulator exceeded safety ceiling — unbounded?")
    return results
