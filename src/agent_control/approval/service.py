"""Approval grant, reject, evaluate, and consume (Slice 6A)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent_control.approval.events import (
    append_approval_granted,
    append_approval_rejected,
    append_fix_authorized,
    append_fix_requested,
)
from agent_control.approval.base_refs import resolve_approval_base_refs
from agent_control.approval.plan_lookup import PlanResolutionError, PlanRunRecord, resolve_plan_for_target
from agent_control.approval.storage import load_approval, save_approval
from agent_control.project_identity import canonical_project
from agent_shared.hash_utils import hash_command_text
from agent_shared.models.approval import (
    ApprovalRejected,
    FixAuthorizedEvent,
    FixRequestedEvent,
    WorkItemApproval,
)

DEFAULT_TTL_HOURS = 72


@dataclass
class FixEvaluation:
    policy_decision: str
    reason: str | None = None
    approval: WorkItemApproval | None = None
    plan_record: PlanRunRecord | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _expires_at(hours: int = DEFAULT_TTL_HOURS) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def _is_expired(approval: WorkItemApproval) -> bool:
    try:
        expires = datetime.fromisoformat(approval.expires_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    return datetime.now(timezone.utc) >= expires


def build_approval_from_plan(
    record: PlanRunRecord,
    *,
    approved_by_login: str,
    source_comment_id: int | None = None,
    source_event_id: str | None = None,
    source_url: str | None = None,
    command_text: str | None = None,
) -> WorkItemApproval:
    approval_id = f"appr-{uuid.uuid4().hex[:16]}"
    approved_base_ref, approved_base = resolve_approval_base_refs(record.project)
    return WorkItemApproval(
        approval_id=approval_id,
        approval_target_id=record.approval_target_id,
        plan_alias=record.plan_alias,
        plan_run_id=record.run_id,
        plan_hash=record.plan_hash,
        blast_radius_hash=record.blast_radius_hash,
        project=record.project,
        issue_id=record.issue_id,
        allowed_files=record.allowed_files,
        approved_by_login=approved_by_login,
        approved_at=_now_iso(),
        expires_at=_expires_at(),
        status="approved",
        approved_base_ref=approved_base_ref,
        approved_base_sha=approved_base,
        source_comment_id=source_comment_id,
        source_event_id=source_event_id,
        source_url=source_url,
        approval_command_text_hash=hash_command_text(command_text) if command_text else None,
    )


def grant_approval(
    state_root: Path,
    *,
    project: str,
    issue_id: int,
    target: str,
    approver_login: str,
    author_is_owner: bool,
    comment_id: int | None = None,
    source_url: str | None = None,
    command_text: str | None = None,
) -> tuple[WorkItemApproval | None, str, bool]:
    """Return (approval, message, event_created)."""
    if not author_is_owner:
        return None, "Rejected — owner approval required", False

    try:
        record = resolve_plan_for_target(state_root, project, issue_id, target)
    except PlanResolutionError as exc:
        return None, str(exc), False

    existing = load_approval(state_root, project, record.approval_target_id)
    if existing and existing.status == "approved" and not _is_expired(existing):
        _, created = append_approval_granted(
            state_root,
            approval=existing,
            comment_id=comment_id,
        )
        return existing, "Approval already active (idempotent replay)", created

    approval = build_approval_from_plan(
        record,
        approved_by_login=approver_login,
        source_comment_id=comment_id,
        source_url=source_url,
        command_text=command_text,
    )
    save_approval(state_root, approval)
    _, created = append_approval_granted(state_root, approval=approval, comment_id=comment_id)
    scope_note = ""
    if not approval.allowed_files:
        scope_note = " Approval recorded; plan lacks explicit file scope — patch generation blocked until replan."
    return approval, f"Approval granted.{scope_note}", created


def reject_approval(
    state_root: Path,
    *,
    project: str,
    issue_id: int,
    target: str,
    rejector_login: str,
    author_is_owner: bool,
    reject_reason: str | None = None,
    comment_id: int | None = None,
) -> tuple[bool, str, bool]:
    if not author_is_owner:
        return False, "Rejected — owner approval required", False

    try:
        record = resolve_plan_for_target(state_root, project, issue_id, target)
    except PlanResolutionError as exc:
        return False, str(exc), False

    body = ApprovalRejected(
        approval_target_id=record.approval_target_id,
        plan_run_id=record.run_id,
        plan_alias=record.plan_alias,
        project=canonical_project(project),
        issue_id=issue_id,
        rejected_by_login=rejector_login,
        rejected_at=_now_iso(),
        reject_reason=reject_reason,
        source_comment_id=comment_id,
    )
    _, created = append_approval_rejected(state_root, body=body, comment_id=comment_id)
    return True, "Approval rejected", created


def evaluate_fix_request(
    state_root: Path,
    *,
    project: str,
    issue_id: int,
    target: str,
) -> FixEvaluation:
    try:
        record = resolve_plan_for_target(state_root, project, issue_id, target)
    except PlanResolutionError as exc:
        return FixEvaluation(policy_decision="blocked", reason=str(exc))

    approval = load_approval(state_root, project, record.approval_target_id)
    if approval is None:
        return FixEvaluation(
            policy_decision="blocked",
            reason="No approval for this plan run; use /agent approve",
            plan_record=record,
        )
    if approval.status == "consumed":
        return FixEvaluation(
            policy_decision="blocked",
            reason="Approval already consumed",
            approval=approval,
            plan_record=record,
        )
    if approval.status == "reserved":
        return FixEvaluation(
            policy_decision="blocked",
            reason="Approval reserved by an in-flight fix run",
            approval=approval,
            plan_record=record,
        )
    if approval.status == "claimed":
        return FixEvaluation(
            policy_decision="blocked",
            reason="Approval claimed by an in-flight publish job",
            approval=approval,
            plan_record=record,
        )
    if approval.status != "approved":
        return FixEvaluation(
            policy_decision="blocked",
            reason=f"Approval status is {approval.status}",
            approval=approval,
            plan_record=record,
        )
    if _is_expired(approval):
        return FixEvaluation(
            policy_decision="blocked",
            reason="Approval expired",
            approval=approval,
            plan_record=record,
        )
    if approval.plan_hash != record.plan_hash:
        return FixEvaluation(
            policy_decision="blocked",
            reason="Plan hash mismatch — replan required",
            approval=approval,
            plan_record=record,
        )
    if approval.blast_radius_hash != record.blast_radius_hash:
        return FixEvaluation(
            policy_decision="blocked",
            reason="Blast radius hash mismatch",
            approval=approval,
            plan_record=record,
        )
    if approval.issue_id != issue_id or approval.project != canonical_project(project):
        return FixEvaluation(
            policy_decision="blocked",
            reason="Project or issue mismatch",
            approval=approval,
            plan_record=record,
        )
    return FixEvaluation(
        policy_decision="approved",
        approval=approval,
        plan_record=record,
    )


def record_fix_request(
    state_root: Path,
    *,
    project: str,
    issue_id: int,
    target: str,
    requested_by_login: str | None,
    comment_id: int | None,
    evaluation: FixEvaluation,
) -> tuple[Path, bool]:
    body = FixRequestedEvent(
        approval_target_id=target if target.startswith("WI-") else (
            evaluation.plan_record.approval_target_id if evaluation.plan_record else target
        ),
        project=canonical_project(project),
        issue_id=issue_id,
        policy_decision="approved" if evaluation.policy_decision == "approved" else "blocked",
        reason=evaluation.reason,
        requested_by_login=requested_by_login,
    )
    if evaluation.plan_record:
        body = body.model_copy(update={"approval_target_id": evaluation.plan_record.approval_target_id})
    return append_fix_requested(state_root, body=body, comment_id=comment_id)


def consume_approval(
    state_root: Path,
    approval: WorkItemApproval,
    *,
    consumed_by_run_id: str,
    consumed_event_id: str,
) -> WorkItemApproval:
    updated = approval.model_copy(
        update={
            "status": "consumed",
            "consumed_at": _now_iso(),
            "consumed_by_run_id": consumed_by_run_id,
            "consumed_event_id": consumed_event_id,
        }
    )
    save_approval(state_root, updated)
    return updated


def authorize_fix(
    state_root: Path,
    *,
    evaluation: FixEvaluation,
    comment_id: int | None,
) -> tuple[FixAuthorizedEvent | None, Path | None, bool]:
    """Record fix authorization without consuming approval (Slice 6B enqueue consumes)."""
    if evaluation.policy_decision != "approved" or evaluation.approval is None or evaluation.plan_record is None:
        return None, None, False

    body = FixAuthorizedEvent(
        approval_id=evaluation.approval.approval_id,
        approval_target_id=evaluation.approval.approval_target_id,
        plan_run_id=evaluation.plan_record.run_id,
        plan_hash=evaluation.approval.plan_hash,
        blast_radius_hash=evaluation.approval.blast_radius_hash,
        project=evaluation.approval.project,
        issue_id=evaluation.approval.issue_id,
        dry_run=False,
        worker_enqueued=False,
        dispatch_target="none",
    )
    path, created = append_fix_authorized(state_root, body=body, comment_id=comment_id)
    return body, path, created


def reserve_approval_for_fix(
    state_root: Path,
    approval: WorkItemApproval,
    *,
    fix_run_id: str,
) -> WorkItemApproval:
    updated = approval.model_copy(
        update={
            "status": "reserved",
            "reserved_at": _now_iso(),
            "reserved_by_fix_run_id": fix_run_id,
        }
    )
    save_approval(state_root, updated)
    return updated


def claim_approval_for_publish(
    state_root: Path,
    approval: WorkItemApproval,
    *,
    publish_job_id: str,
) -> WorkItemApproval | None:
    """Atomically claim a reserved/approved approval for a publish job.

    Returns None if the approval cannot be claimed (revoked, already claimed
    by another job, or consumed).
    """
    current = load_approval(state_root, approval.project, approval.approval_target_id)
    if current is None:
        return None
    if current.status == "claimed" and current.claimed_by_publish_job_id == publish_job_id:
        return current
    if current.status not in ("reserved", "approved"):
        return None
    if current.status == "claimed":
        return None
    updated = current.model_copy(
        update={
            "status": "claimed",
            "claimed_at": _now_iso(),
            "claimed_by_publish_job_id": publish_job_id,
        }
    )
    save_approval(state_root, updated)
    return updated


def release_approval_claim(
    state_root: Path,
    approval: WorkItemApproval,
) -> WorkItemApproval:
    """Release a publish claim back to reserved (or approved if never reserved)."""
    current = load_approval(state_root, approval.project, approval.approval_target_id)
    if current is None or current.status != "claimed":
        return approval
    back = "reserved" if current.reserved_by_fix_run_id else "approved"
    updated = current.model_copy(
        update={
            "status": back,
            "claimed_at": None,
            "claimed_by_publish_job_id": None,
        }
    )
    save_approval(state_root, updated)
    return updated


def release_approval_reservation(
    state_root: Path,
    approval: WorkItemApproval,
    *,
    fix_run_id: str,
    reason: str,
) -> WorkItemApproval:
    if approval.status not in ("reserved", "approved", "claimed"):
        return approval
    updated = approval.model_copy(
        update={
            "status": "approved",
            "reserved_at": None,
            "reserved_by_fix_run_id": None,
            "claimed_at": None,
            "claimed_by_publish_job_id": None,
            "publish_state": None,
        }
    )
    save_approval(state_root, updated)
    return updated


def mark_branch_published(
    state_root: Path,
    approval: WorkItemApproval,
    *,
    fix_run_id: str,
) -> WorkItemApproval:
    updated = approval.model_copy(update={"publish_state": "branch_published"})
    save_approval(state_root, updated)
    return updated


def consume_approval_on_pr_open(
    state_root: Path,
    approval: WorkItemApproval,
    *,
    fix_run_id: str,
    consumed_event_id: str = "",
) -> WorkItemApproval:
    if approval.status == "consumed":
        return approval
    # Prefer latest disk state (may be claimed)
    current = load_approval(state_root, approval.project, approval.approval_target_id) or approval
    return consume_approval(
        state_root,
        current,
        consumed_by_run_id=fix_run_id,
        consumed_event_id=consumed_event_id or f"ingest-{fix_run_id}",
    )


def consume_approval_for_fix(
    state_root: Path,
    approval: WorkItemApproval,
    *,
    fix_run_id: str,
    consumed_event_id: str,
) -> WorkItemApproval:
    return consume_approval(
        state_root,
        approval,
        consumed_by_run_id=fix_run_id,
        consumed_event_id=consumed_event_id,
    )
