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


def normalize_workflow_path(path: str | None) -> str:
    """Normalize Gitea/Actions workflow identity paths for comparison.

    Gitea often returns ``ci.yaml@refs/pull/20/head`` while our required matrix
    uses ``.gitea/workflows/ci.yaml``.
    """
    text = (path or "").replace("\\", "/").strip()
    if not text:
        return ""
    if "@" in text:
        text = text.split("@", 1)[0].strip()
    return text.strip("/")


def workflow_paths_match(required: str | None, observed: str | None) -> bool:
    """True when required and observed path refer to the same workflow file."""
    req = normalize_workflow_path(required)
    obs = normalize_workflow_path(observed)
    if not req or not obs:
        return False
    if req == obs:
        return True
    if req.endswith("/" + obs) or obs.endswith("/" + req):
        return True
    return False


def _obs_matches_required(req: RequiredWorkflow, obs: WorkflowObservation) -> bool:
    if req.workflow_id and obs.workflow_id and req.workflow_id == obs.workflow_id:
        return True
    if req.path and obs.path and workflow_paths_match(req.path, obs.path):
        return True
    if (
        req.display_name
        and obs.display_name
        and req.display_name.lower() == obs.display_name.lower()
        and not req.path
        and not obs.path
    ):
        return True
    return False


def _latest_for_required(
    req: RequiredWorkflow,
    observations: list[WorkflowObservation],
) -> WorkflowObservation | None:
    matches = [o for o in observations if _obs_matches_required(req, o)]
    if not matches:
        return None
    return max(matches, key=lambda o: (o.run_attempt, str(o.workflow_run_id)))


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
            # Exact duplicate payload — still re-evaluate (matcher/rules may have improved)
            return evaluate_aggregate(result)
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

    missing: list[str] = []
    any_failing = False
    all_success = True

    for req in required:
        label = req.path or req.display_name or req.workflow_id or "required"
        obs = _latest_for_required(req, sha_obs)
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
