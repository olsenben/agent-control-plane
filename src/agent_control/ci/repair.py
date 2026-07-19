"""Repair gate, locks, and reservation (Slice 6F.2)."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from agent_control.aci.backends.base import SandboxAttestation
from agent_control.ci.aggregate import workflow_paths_match
from agent_control.config import Settings, get_settings
from agent_shared.models.ci import (
    AUTO_REPAIRABLE_FAILURE_CLASSES,
    CiVerificationResult,
    FailureEvidenceManifest,
    PendingCiRecord,
)
from agent_shared.repo_identity import split_repo_full_name

logger = logging.getLogger(__name__)


@dataclass
class RepairGateResult:
    allowed: bool
    reason_codes: list[str]
    label: str = "agent:blocked"  # or agent:needs-human
    repair_key: str = ""


def repair_key(owner: str, repo: str, pr_number: int | None, expected_head_sha: str) -> str:
    pr = "none" if pr_number is None else str(pr_number)
    return f"repair:{owner}/{repo}:{pr}:{expected_head_sha}"


def all_required_workflows_terminal(result: CiVerificationResult) -> bool:
    """True when every required workflow has a latest observation for the expected SHA."""
    if not result.required_workflows:
        return False
    if result.missing_workflows:
        return False
    sha = result.expected_head_commit_sha
    for req in result.required_workflows:
        matched = False
        for obs in result.observations:
            if obs.head_sha != sha:
                continue
            if req.workflow_id and obs.workflow_id and req.workflow_id == obs.workflow_id:
                matched = True
                break
            if req.path and obs.path and workflow_paths_match(req.path, obs.path):
                matched = True
                break
        if not matched:
            return False
        # conclusion present implies terminal for our observe path
    return True


def evaluate_repair_allowed(
    *,
    settings: Settings,
    result: CiVerificationResult,
    pending: PendingCiRecord,
    evidence: FailureEvidenceManifest | None,
    attestation: SandboxAttestation | None,
    current_pr_head: str | None,
    repair_attempt_count: int,
    branch_ok: bool,
    no_unrecognized_commits: bool,
    effective_command_policy_hash: str | None = None,
    expected_effective_command_policy_hash: str | None = None,
    tool_policy_execution_allowed: bool | None = None,
) -> RepairGateResult:
    reasons: list[str] = []
    label = "agent:blocked"
    owner, repo = split_repo_full_name(pending.repository)
    key = repair_key(
        owner,
        repo,
        pending.opened_pr_number,
        pending.expected_head_commit_sha,
    )

    if not settings.fix_ci_observe_enabled:
        reasons.append("observe_disabled")
    if not settings.fix_ci_failure_evidence_enabled:
        reasons.append("evidence_disabled")
    if not settings.fix_ci_repair_enabled:
        reasons.append("repair_disabled")

    if result.expected_head_commit_sha != pending.expected_head_commit_sha:
        reasons.append("exact_sha_mismatch")
    if not all_required_workflows_terminal(result):
        reasons.append("required_workflows_not_terminal")
    if result.verdict != "failing":
        reasons.append(f"verdict_not_failing:{result.verdict}")
    if result.missing_workflows:
        reasons.append("missing_required_workflows")

    if evidence is None or evidence.status != "collected":
        reasons.append("evidence_not_collected")
        if evidence is not None and evidence.status in ("unavailable", "contract_mismatch"):
            label = "agent:blocked"
    elif evidence.expected_head_commit_sha != pending.expected_head_commit_sha:
        reasons.append("evidence_sha_mismatch")
    elif not evidence.has_terminal_failed_job:
        reasons.append("evidence_missing_failed_job")

    failure_class = evidence.failure_class if evidence else "unknown"
    if failure_class not in AUTO_REPAIRABLE_FAILURE_CLASSES:
        reasons.append(f"failure_class_not_auto:{failure_class}")
        if failure_class in ("unknown",):
            label = "agent:needs-human"

    if not branch_ok:
        reasons.append("branch_policy")
        label = "agent:needs-human"
    if not no_unrecognized_commits:
        reasons.append("unrecognized_branch_commits")
        label = "agent:needs-human"

    max_attempts = settings.fix_ci_repair_max_attempts
    if repair_attempt_count >= max_attempts:
        reasons.append("repair_budget_exhausted")
        label = "agent:needs-human"

    if attestation is None or attestation.mode != "strong":
        reasons.append("sandbox_attestation_not_strong")
        label = "agent:blocked"
    elif (
        settings.sandbox_expected_policy_hash
        and attestation.policy_hash != settings.sandbox_expected_policy_hash
    ):
        reasons.append("sandbox_policy_hash_mismatch")
        label = "agent:blocked"

    if tool_policy_execution_allowed is False:
        reasons.append("tool_policy_empty_allowance")
        label = "agent:blocked"
    if (
        expected_effective_command_policy_hash
        and effective_command_policy_hash
        and expected_effective_command_policy_hash != effective_command_policy_hash
    ):
        reasons.append("effective_command_policy_hash_mismatch")
        label = "agent:blocked"

    if current_pr_head is None or current_pr_head != pending.expected_head_commit_sha:
        reasons.append("pr_head_mismatch")

    allowed = not reasons
    return RepairGateResult(
        allowed=allowed,
        reason_codes=reasons,
        label=label if not allowed else "",
        repair_key=key,
    )


def repair_lock_dir(state_root: Path) -> Path:
    return state_root / "locks" / "repair"


def acquire_pr_lock(
    state_root: Path,
    *,
    repository: str,
    pr_number: int | None,
    holder: str,
) -> Path | None:
    """Exclusive-create lock file for repo+PR. Returns path or None if held."""
    owner, repo = split_repo_full_name(repository)
    pr = "none" if pr_number is None else str(pr_number)
    path = repair_lock_dir(state_root) / owner / repo / f"pr-{pr}.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"holder": holder, "repository": repository, "pr_number": pr_number})
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        fd = os.open(path, flags, 0o644)
    except FileExistsError:
        return None
    try:
        os.write(fd, payload.encode("utf-8"))
    finally:
        os.close(fd)
    return path


def release_pr_lock(lock_path: Path | None) -> None:
    if lock_path is None:
        return
    try:
        lock_path.unlink(missing_ok=True)
    except OSError:
        logger.exception("repair_lock_release_failed path=%s", lock_path)


def reserve_repair_attempt(
    state_root: Path,
    repair_key_value: str,
    *,
    max_attempts: int,
) -> int | None:
    """Atomically increment attempt counter; return new attempt (1-based) or None if exhausted."""
    path = repair_lock_dir(state_root) / "attempts" / f"{repair_key_value.replace(':', '_')}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    current = 0
    if path.is_file():
        try:
            current = int(json.loads(path.read_text(encoding="utf-8")).get("repair_attempt", 0))
        except (json.JSONDecodeError, ValueError, TypeError):
            current = 0
    if current >= max_attempts:
        return None
    new_val = current + 1
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"repair_attempt": new_val}), encoding="utf-8")
    os.replace(tmp, path)
    return new_val


def get_repair_attempt_count(state_root: Path, repair_key_value: str) -> int:
    path = repair_lock_dir(state_root) / "attempts" / f"{repair_key_value.replace(':', '_')}.json"
    if not path.is_file():
        return 0
    try:
        return int(json.loads(path.read_text(encoding="utf-8")).get("repair_attempt", 0))
    except (json.JSONDecodeError, ValueError, TypeError):
        return 0


def consider_repair_dispatch(
    state_root: Path,
    *,
    result: CiVerificationResult,
    pending: PendingCiRecord,
    evidence: FailureEvidenceManifest | None,
    attestation: SandboxAttestation | None,
    current_pr_head: str | None = None,
    branch_ok: bool = True,
    no_unrecognized_commits: bool = True,
    allowed_files: list[str] | None = None,
    required_command_ids: list[str] | None = None,
    settings: Settings | None = None,
) -> dict:
    """Evaluate gate under short observer lock; create durable reservation.

    Does not enqueue and does not hold the observer lock for the worker.
    Caller must: enqueue → emit requested → release observer lock.
    """
    from agent_control.ci.reservation import (
        LINEAGE_MAX_ATTEMPTS_V1,
        RepairReservation,
        create_repair_reservation,
        get_lineage_attempt_count,
        increment_lineage_attempt,
        load_repair_reservation,
    )

    settings = settings or get_settings()
    lineage_id = pending.fix_run_id
    key_preview = repair_key(
        *split_repo_full_name(pending.repository),
        pending.opened_pr_number,
        pending.expected_head_commit_sha,
    )
    existing_early = load_repair_reservation(state_root, key_preview)
    if existing_early is not None:
        return {
            "dispatched": False,
            "blocked": True,
            "reason_codes": ["reservation_exists"],
            "label": "agent:blocked",
            "repair_key": key_preview,
            "existing_job_id": existing_early.job_id,
        }

    attempt_count = get_lineage_attempt_count(state_root, lineage_id)

    from agent_control.gitea_client import GiteaClient
    from agent_control.project_registry import PolicySourcePinError, resolve_policy_source_pin
    from agent_control.sandbox.tool_policy import (
        TOOLS_RELATIVE_PATH,
        intersect_command_ids,
        load_tool_policy_from_text,
    )

    try:
        pin = resolve_policy_source_pin(pending.repository, settings=settings)
    except PolicySourcePinError as exc:
        logger.warning("repair_policy_pin_failed repo=%s err=%s", pending.repository, exc)
        return {
            "dispatched": False,
            "blocked": True,
            "reason_codes": ["policy_source_pin_unresolved"],
            "label": "agent:blocked",
            "repair_key": key_preview,
        }

    tools_text: str | None = None
    try:
        owner, repo = split_repo_full_name(pin.policy_source_repo)
        tools_text = GiteaClient(settings).get_file_raw(
            owner,
            repo,
            TOOLS_RELATIVE_PATH,
            ref=pin.policy_source_sha,
        )
    except Exception as exc:
        logger.warning(
            "repair_tools_yaml_fetch_failed repo=%s sha=%s err=%s",
            pending.repository,
            pin.policy_source_sha,
            exc,
        )
        tools_text = None

    tool_policy = load_tool_policy_from_text(
        tools_text,
        loaded_path=TOOLS_RELATIVE_PATH,
    )
    mapped_ids = list(required_command_ids or [])
    effective_ids = intersect_command_ids(mapped_ids, tool_policy.allowed_command_ids)

    gate = evaluate_repair_allowed(
        settings=settings,
        result=result,
        pending=pending,
        evidence=evidence,
        attestation=attestation,
        current_pr_head=current_pr_head or pending.expected_head_commit_sha,
        repair_attempt_count=attempt_count,
        branch_ok=branch_ok,
        no_unrecognized_commits=no_unrecognized_commits,
        effective_command_policy_hash=tool_policy.effective_command_policy_hash,
        expected_effective_command_policy_hash=tool_policy.effective_command_policy_hash,
        tool_policy_execution_allowed=bool(effective_ids) and tool_policy.execution_allowed,
    )
    if not gate.allowed:
        return {
            "dispatched": False,
            "blocked": True,
            "reason_codes": gate.reason_codes,
            "label": gate.label,
            "repair_key": gate.repair_key,
        }

    # Short-lived observer coordination lock only
    lock = acquire_pr_lock(
        state_root,
        repository=pending.repository,
        pr_number=pending.opened_pr_number,
        holder=f"observe:{pending.fix_run_id}",
    )
    if lock is None:
        return {
            "dispatched": False,
            "blocked": True,
            "reason_codes": ["observer_lock_held"],
            "label": "agent:blocked",
            "repair_key": gate.repair_key,
        }
    try:
        if current_pr_head and current_pr_head != pending.expected_head_commit_sha:
            return {
                "dispatched": False,
                "blocked": True,
                "reason_codes": ["pr_head_changed_after_lock"],
                "label": "agent:blocked",
                "repair_key": gate.repair_key,
                "lock_path": str(lock),
            }

        existing = load_repair_reservation(state_root, gate.repair_key)
        if existing is not None:
            return {
                "dispatched": False,
                "blocked": True,
                "reason_codes": ["reservation_exists"],
                "label": "agent:blocked",
                "repair_key": gate.repair_key,
                "lock_path": str(lock),
                "existing_job_id": existing.job_id,
            }

        max_attempts = min(settings.fix_ci_repair_max_attempts, LINEAGE_MAX_ATTEMPTS_V1)
        reserved = increment_lineage_attempt(
            state_root, lineage_id, max_attempts=max_attempts
        )
        if reserved is None:
            return {
                "dispatched": False,
                "blocked": True,
                "reason_codes": ["repair_budget_exhausted"],
                "label": "agent:needs-human",
                "repair_key": gate.repair_key,
                "lock_path": str(lock),
            }

        reservation = RepairReservation(
            repair_key=gate.repair_key,
            repository=pending.repository,
            pr_number=pending.opened_pr_number,
            expected_head_commit_sha=pending.expected_head_commit_sha,
            repair_attempt=reserved,
            fix_run_id=pending.fix_run_id,
            repair_lineage_id=lineage_id,
            evidence_observation_id=(
                evidence.evidence_observation_id if evidence else ""
            ),
            agent_branch=pending.agent_branch or "",
            allowed_files=list(allowed_files or []),
            required_command_ids=list(effective_ids),
            issue_id=pending.issue_id,
            artifact_root=pending.artifact_root,
            policy_source_repo=pin.policy_source_repo,
            policy_source_remote=pin.policy_source_remote,
            policy_source_ref=pin.policy_source_ref,
            policy_source_sha=pin.policy_source_sha,
            policy_schema_version=pin.policy_schema_version,
            allowed_command_ids=list(tool_policy.allowed_command_ids),
            command_constraints={
                cid: c.to_dict() for cid, c in tool_policy.constraints.items()
            },
            command_registry_hash=tool_policy.command_registry_hash,
            effective_command_policy_hash=tool_policy.effective_command_policy_hash,
            tool_policy_status=tool_policy.status,
        )
        created = create_repair_reservation(state_root, reservation)
        if created is None:
            return {
                "dispatched": False,
                "blocked": True,
                "reason_codes": ["reservation_exists"],
                "label": "agent:blocked",
                "repair_key": gate.repair_key,
                "lock_path": str(lock),
            }
        return {
            "dispatched": True,
            "blocked": False,
            "repair_attempt": reserved,
            "repair_key": gate.repair_key,
            "repair_lineage_id": lineage_id,
            "reason_codes": [],
            "label": "",
            "lock_path": str(lock),
            "reservation": created.to_dict(),
        }
    except Exception:
        release_pr_lock(lock)
        raise
