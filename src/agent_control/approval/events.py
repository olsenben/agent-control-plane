"""Idempotent approval ledger events."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_control.events import AgentEvent, append_event, deterministic_event_id
from agent_control.project_identity import canonical_project
from agent_shared.models.approval import (
    ApprovalConsumedEvent,
    ApprovalRejected,
    ApprovalReleasedEvent,
    ApprovalReservedEvent,
    FixAuthorizedEvent,
    FixEnqueuedEvent,
    FixRequestedEvent,
    WorkItemApproval,
)


def _delivery_id(
    *,
    comment_id: str | int | None,
    command_kind: str,
    project: str,
    issue_id: int,
    approval_target: str,
) -> str:
    cid = str(comment_id or "none")
    repo = canonical_project(project)
    return f"{cid}:{command_kind}:{repo}:{issue_id}:{approval_target}"


def append_approval_event(
    state_root: Path,
    *,
    event_type: str,
    project: str,
    comment_id: str | int | None,
    command_kind: str,
    issue_id: int,
    approval_target: str,
    payload: dict[str, Any],
) -> tuple[Path, bool]:
    delivery = _delivery_id(
        comment_id=comment_id,
        command_kind=command_kind,
        project=project,
        issue_id=issue_id,
        approval_target=approval_target,
    )
    event_id = deterministic_event_id("ct103", delivery, event_type)
    event = AgentEvent(
        event_id=event_id,
        type=event_type,
        raw_event_type=event_type,
        source="ct103",
        delivery_id=delivery,
        project=canonical_project(project),
        payload=payload,
        recorded_at=datetime.now(timezone.utc).isoformat(),
    )
    return append_event(state_root, event)


def append_fix_requested(
    state_root: Path,
    *,
    body: FixRequestedEvent,
    comment_id: str | int | None,
    command_kind: str = "fix",
) -> tuple[Path, bool]:
    return append_approval_event(
        state_root,
        event_type="agent.fix_requested",
        project=body.project,
        comment_id=comment_id,
        command_kind=command_kind,
        issue_id=body.issue_id,
        approval_target=body.approval_target_id,
        payload=body.model_dump(mode="json"),
    )


def append_approval_granted(
    state_root: Path,
    *,
    approval: WorkItemApproval,
    comment_id: str | int | None,
) -> tuple[Path, bool]:
    return append_approval_event(
        state_root,
        event_type="human.approval_granted",
        project=approval.project,
        comment_id=comment_id,
        command_kind="approve",
        issue_id=approval.issue_id,
        approval_target=approval.approval_target_id,
        payload=approval.model_dump(mode="json"),
    )


def append_approval_rejected(
    state_root: Path,
    *,
    body: ApprovalRejected,
    comment_id: str | int | None,
) -> tuple[Path, bool]:
    return append_approval_event(
        state_root,
        event_type="human.approval_rejected",
        project=body.project,
        comment_id=comment_id,
        command_kind="reject",
        issue_id=body.issue_id,
        approval_target=body.approval_target_id,
        payload=body.model_dump(mode="json"),
    )


def append_fix_authorized(
    state_root: Path,
    *,
    body: FixAuthorizedEvent,
    comment_id: str | int | None,
) -> tuple[Path, bool]:
    return append_approval_event(
        state_root,
        event_type="agent.fix_authorized",
        project=body.project,
        comment_id=comment_id,
        command_kind="fix",
        issue_id=body.issue_id,
        approval_target=body.approval_target_id,
        payload=body.model_dump(mode="json"),
    )


def append_approval_reserved(
    state_root: Path,
    *,
    body: ApprovalReservedEvent,
    comment_id: str | int | None,
) -> tuple[Path, bool]:
    return append_approval_event(
        state_root,
        event_type="agent.approval_reserved",
        project=body.project,
        comment_id=comment_id,
        command_kind="fix",
        issue_id=body.issue_id,
        approval_target=body.approval_target_id,
        payload=body.model_dump(mode="json"),
    )


def append_approval_released(
    state_root: Path,
    *,
    body: ApprovalReleasedEvent,
    comment_id: str | int | None,
) -> tuple[Path, bool]:
    return append_approval_event(
        state_root,
        event_type="agent.approval_released",
        project=body.project,
        comment_id=comment_id,
        command_kind="fix",
        issue_id=body.issue_id,
        approval_target=body.approval_target_id,
        payload=body.model_dump(mode="json"),
    )


def append_approval_consumed(
    state_root: Path,
    *,
    body: ApprovalConsumedEvent,
    comment_id: str | int | None,
) -> tuple[Path, bool]:
    return append_approval_event(
        state_root,
        event_type="agent.approval_consumed",
        project=body.project,
        comment_id=comment_id,
        command_kind="fix",
        issue_id=body.issue_id,
        approval_target=body.approval_target_id,
        payload=body.model_dump(mode="json"),
    )


def append_fix_enqueued(
    state_root: Path,
    *,
    body: FixEnqueuedEvent,
    comment_id: str | int | None,
) -> tuple[Path, bool]:
    delivery = _delivery_id(
        comment_id=comment_id,
        command_kind="fix_enqueued",
        project=body.project,
        issue_id=body.issue_id,
        approval_target=body.approval_target_id,
    )
    delivery = f"{delivery}:{body.fix_run_id}"
    event_id = deterministic_event_id("ct103", delivery, "agent.fix_enqueued")
    event = AgentEvent(
        event_id=event_id,
        type="agent.fix_enqueued",
        raw_event_type="agent.fix_enqueued",
        source="ct103",
        delivery_id=delivery,
        project=canonical_project(body.project),
        payload=body.model_dump(mode="json"),
        recorded_at=datetime.now(timezone.utc).isoformat(),
    )
    return append_event(state_root, event)
