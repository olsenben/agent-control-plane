"""Aggregate CI verdict reducer (Slice 6E.1)."""

from __future__ import annotations

from datetime import datetime, timezone

from agent_shared.models.ci import (
    CiVerificationResult,
    CiVerdict,
    NormalizedConclusion,
    PendingCiRecord,
    RequiredWorkflow,
    WorkflowObservation,
)

_FAIL_CONCLUSIONS: frozenset[NormalizedConclusion] = frozenset(
    {"failure", "cancelled", "timed_out", "unknown"}
)
_SUCCESS: NormalizedConclusion = "success"


def normalize_conclusion(raw: str | None, *, status: str | None = None) -> NormalizedConclusion:
    """Unknown / malformed → fail closed (unknown)."""
    if raw is None or not str(raw).strip():
        if status and status not in ("completed", "success", "failure"):
            return "unknown"
        return "unknown"
    value = str(raw).strip().lower()
    mapping: dict[str, NormalizedConclusion] = {
        "success": "success",
        "failure": "failure",
        "cancelled": "cancelled",
        "canceled": "cancelled",
        "timed_out": "timed_out",
        "timeout": "timed_out",
        "skipped": "skipped",
        "neutral": "unknown",
        "action_required": "unknown",
        "startup_failure": "failure",
    }
    return mapping.get(value, "unknown")


def _workflow_key(obs: WorkflowObservation) -> str:
    if obs.workflow_id:
        return f"id:{obs.workflow_id}"
    if obs.path:
        return f"path:{obs.path.replace(chr(92), '/')}"
    return f"name:{obs.display_name.lower()}"


def _required_key(req: RequiredWorkflow) -> str:
    if req.workflow_id:
        return f"id:{req.workflow_id}"
    if req.path:
        return f"path:{req.path.replace(chr(92), '/')}"
    return f"name:{req.display_name.lower()}"


def _latest_by_workflow(observations: list[WorkflowObservation]) -> dict[str, WorkflowObservation]:
    latest: dict[str, WorkflowObservation] = {}
    for obs in observations:
        key = _workflow_key(obs)
        prev = latest.get(key)
        if prev is None or obs.run_attempt >= prev.run_attempt:
            latest[key] = obs
    return latest


def merge_observation(
    result: CiVerificationResult,
    observation: WorkflowObservation,
) -> CiVerificationResult:
    """Append or replace observation by (workflow_run_id, attempt, status) idempotency."""
    observations = list(result.observations)
    for idx, existing in enumerate(observations):
        if (
            existing.workflow_run_id == observation.workflow_run_id
            and existing.run_attempt == observation.run_attempt
            and existing.status == observation.status
            and existing.conclusion == observation.conclusion
        ):
            # Exact duplicate — keep first (idempotent)
            return result
        if (
            existing.workflow_run_id == observation.workflow_run_id
            and existing.run_attempt == observation.run_attempt
        ):
            observations[idx] = observation
            break
    else:
        observations.append(observation)
    updated = result.model_copy(update={"observations": observations})
    return evaluate_aggregate(updated)


def evaluate_aggregate(result: CiVerificationResult) -> CiVerificationResult:
    """Derive verdict from required workflows + latest terminal observations.

    Rules:
    - verified only when every required workflow has success for exact expected SHA
    - failing when any required workflow's latest terminal attempt failed/cancelled/timed_out/unknown
    - empty required matrix → pending with reason (never accept arbitrary green CI)
    - pending survives first failure until terminal resolution paths (rerun may recover)
    - Terminal resolution only for verified | superseded | expired (caller sets those)
    """
    now = datetime.now(timezone.utc).isoformat()
    reason_codes: list[str] = []
    required = list(result.required_workflows)
    if not required:
        reason_codes.append("empty_required_matrix")
        return result.model_copy(
            update={
                "verdict": "pending",
                "missing_workflows": [],
                "evaluated_at": now,
                "reason_codes": reason_codes,
            }
        )

    # Filter observations to exact expected SHA
    sha_obs = [
        o
        for o in result.observations
        if o.head_sha == result.expected_head_commit_sha
    ]
    latest = _latest_by_workflow(sha_obs)

    missing: list[str] = []
    any_failing = False
    all_success = True

    for req in required:
        key = _required_key(req)
        label = req.path or req.display_name or req.workflow_id or key
        obs = latest.get(key)
        # Also try matching by path/name loosely if id missing
        if obs is None:
            for candidate in latest.values():
                if req.path and candidate.path.replace("\\", "/") == req.path.replace("\\", "/"):
                    obs = candidate
                    break
                if (
                    req.display_name
                    and candidate.display_name.lower() == req.display_name.lower()
                    and (not req.path or not candidate.path)
                ):
                    obs = candidate
                    break
        if obs is None:
            missing.append(label)
            all_success = False
            continue
        if obs.conclusion == _SUCCESS:
            continue
        if obs.conclusion in _FAIL_CONCLUSIONS:
            any_failing = True
            all_success = False
            reason_codes.append(f"workflow_failed:{label}:{obs.conclusion}")
        elif obs.conclusion == "skipped":
            # Skipped does not count as success for required workflows
            all_success = False
            missing.append(label)
            reason_codes.append(f"workflow_skipped:{label}")
        else:
            all_success = False

    if missing:
        reason_codes.append("missing_workflows")
        all_success = False

    if all_success and not missing and not any_failing:
        verdict: CiVerdict = "verified"
        reason_codes.append("all_required_workflows_success")
    elif any_failing:
        # Rerun semantics: mark failing but do not terminal-resolve pending record
        verdict = "failing"
    else:
        verdict = "pending"
        if not reason_codes:
            reason_codes.append("awaiting_required_workflows")

    # Preserve terminal superseded/expired if already set on result
    if result.verdict in ("superseded", "expired"):
        verdict = result.verdict

    revision = result.verdict_revision
    if verdict != result.verdict:
        revision = result.verdict_revision + 1

    return result.model_copy(
        update={
            "verdict": verdict,
            "missing_workflows": missing,
            "evaluated_at": now,
            "reason_codes": reason_codes,
            "verdict_revision": revision,
        }
    )


def result_from_pending(record: PendingCiRecord) -> CiVerificationResult:
    return CiVerificationResult(
        fix_run_id=record.fix_run_id,
        repository=record.repository,
        expected_head_commit_sha=record.expected_head_commit_sha,
        verdict=record.current_verdict,
        required_workflows=list(record.required_workflows),
        opened_pr_number=record.opened_pr_number,
        issue_id=record.issue_id,
        verdict_revision=record.verdict_revision,
    )
