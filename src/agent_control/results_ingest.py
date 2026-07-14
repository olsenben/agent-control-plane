"""Ingest CT104 result events into the CT103 event ledger.

``agent.run_completed`` means the run reached a terminal state, not that the agent succeeded.
Failed runs use ``status=failed`` with a ``terminal_status`` of ``failed_*``.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from agent_control.config import Settings, get_settings
from agent_control.events import AgentEvent, append_event, deterministic_event_id
from agent_control.memory.mapper import policy_gate_risk_tags
from agent_control.memory.writeback import writeback_from_completed
from agent_shared.models.events import AgentRunCompletedEvent, RiskTagSourceEntry


def inbox_content_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def ct104_inbox_dir(state_root: Path) -> Path:
    return state_root / "inbox" / "ct104-results"


def _enrich_event_payload(event_model: AgentRunCompletedEvent) -> dict:
    payload = event_model.model_dump(mode="json")
    gate_sources = policy_gate_risk_tags(event_model)
    merged: dict[str, RiskTagSourceEntry] = {
        item.tag: item for item in event_model.risk_tag_sources
    }
    for tag in event_model.risk_tags:
        merged.setdefault(tag, RiskTagSourceEntry(tag=tag, source="model_output"))
    for item in gate_sources:
        merged[item.tag] = RiskTagSourceEntry(tag=item.tag, source=item.source)
    payload["risk_tag_sources"] = [s.model_dump(mode="json") for s in merged.values()]
    payload["risk_tags"] = sorted(merged.keys())
    payload.setdefault("policy_decision", "allow")
    return payload


def handle_fix_ingest_side_effects(
    state_root: Path,
    event: AgentRunCompletedEvent,
) -> None:
    """Consume or release approval based on fix ingest outcome (Slice 6D).

    Also registers pending CI observation when ``fix_status=pr_opened_pending_ci`` (6E.1).
    """
    from agent_control.approval.events import append_approval_consumed, append_approval_released
    from agent_control.approval.storage import load_approval
    from agent_shared.constants import (
        FIX_STATUS_BRANCH_PUBLISHED_PR_FAILED,
        FIX_STATUS_PR_OPENED_PENDING_CI,
        FIX_STATUS_PUBLISH_FAILED,
    )
    from agent_shared.models.approval import ApprovalConsumedEvent, ApprovalReleasedEvent

    if event.command_kind == "fix" and event.fix_status == FIX_STATUS_PR_OPENED_PENDING_CI:
        _register_pending_ci_from_event(state_root, event)

    if event.command_kind != "fix" or not event.approval_id or not event.approval_target_id:
        return
    if event.project is None or event.issue_id is None:
        return
    approval = load_approval(state_root, event.project, event.approval_target_id)
    if approval is None:
        return

    if event.fix_status == FIX_STATUS_PR_OPENED_PENDING_CI:
        from agent_control.approval.service import consume_approval_on_pr_open

        consumed = consume_approval_on_pr_open(
            state_root,
            approval,
            fix_run_id=event.run_id,
            consumed_event_id=f"ingest-{event.run_id}",
        )
        body = ApprovalConsumedEvent(
            approval_id=consumed.approval_id,
            approval_target_id=consumed.approval_target_id,
            plan_run_id=approval.plan_run_id,
            project=consumed.project,
            issue_id=consumed.issue_id,
            consumed_by_fix_run_id=event.run_id,
            consumed_by_event_id=f"ingest-{event.run_id}",
        )
        append_approval_consumed(state_root, body=body, comment_id=None)
        return

    if event.fix_status in (FIX_STATUS_PUBLISH_FAILED, FIX_STATUS_BRANCH_PUBLISHED_PR_FAILED):
        if event.fix_status == FIX_STATUS_PUBLISH_FAILED:
            from agent_control.approval.service import release_approval_reservation

            release_approval_reservation(
                state_root,
                approval,
                fix_run_id=event.run_id,
                reason=event.fix_status or "publish_failed",
            )
            body = ApprovalReleasedEvent(
                approval_id=approval.approval_id,
                approval_target_id=approval.approval_target_id,
                plan_run_id=approval.plan_run_id,
                project=approval.project,
                issue_id=approval.issue_id,
                released_by_fix_run_id=event.run_id,
                reason=event.fix_status or "publish_failed",
            )
            append_approval_released(state_root, body=body, comment_id=None)
        return

    if event.status == "failed" and approval.status == "reserved":
        from agent_control.approval.service import release_approval_reservation

        release_approval_reservation(
            state_root,
            approval,
            fix_run_id=event.run_id,
            reason="fix_run_failed",
        )
        body = ApprovalReleasedEvent(
            approval_id=approval.approval_id,
            approval_target_id=approval.approval_target_id,
            plan_run_id=approval.plan_run_id,
            project=approval.project,
            issue_id=approval.issue_id,
            released_by_fix_run_id=event.run_id,
            reason="fix_run_failed",
        )
        append_approval_released(state_root, body=body, comment_id=None)


def _register_pending_ci_from_event(
    state_root: Path,
    event: AgentRunCompletedEvent,
) -> None:
    if not event.head_commit_sha or not event.project:
        return
    from agent_control.ci.observe import required_workflows_from_hints
    from agent_control.ci.pending import register_pending_ci
    from agent_control.config import get_settings

    settings = get_settings()
    workflow_hints: list[str] = []
    if event.fix_result is not None:
        workflow_hints = list(getattr(event.fix_result, "ci_hints", None) or [])
    required = required_workflows_from_hints(
        workflow_hints,
        require_matrix=settings.fix_ci_require_matrix_match,
        repo_default=(
            settings.fix_ci_repo_default_workflow
            if settings.fix_ci_require_matrix_match
            else None
        ),
    )
    register_pending_ci(
        state_root,
        fix_run_id=event.run_id,
        repository=event.project,
        expected_head_commit_sha=event.head_commit_sha,
        opened_pr_number=event.opened_pr_number,
        issue_id=event.issue_id,
        agent_branch=event.agent_branch,
        required_workflows=required,
        artifact_root=event.artifact_root,
    )


def ingest_result_file(
    state_root: Path,
    path: Path,
    settings: Settings | None = None,
) -> tuple[Path, bool]:
    settings = settings or get_settings()
    data = json.loads(path.read_text(encoding="utf-8"))
    event_model = AgentRunCompletedEvent.model_validate(data)
    event_id = deterministic_event_id(
        "ct104",
        event_model.run_id,
        "agent.run_completed",
    )
    payload = _enrich_event_payload(event_model)
    event = AgentEvent(
        event_id=event_id,
        type="agent.run_completed",
        raw_event_type="agent.run_completed",
        source="ct104",
        delivery_id=event_model.run_id,
        project=event_model.project,
        payload=payload,
    )
    stored_path, created = append_event(state_root, event)
    enriched = event_model.model_copy(
        update={
            "risk_tags": payload["risk_tags"],
            "risk_tag_sources": [
                RiskTagSourceEntry.model_validate(s) for s in payload["risk_tag_sources"]
            ],
            "policy_decision": payload["policy_decision"],
        }
    )
    if event_model.status == "completed" and (
        event_model.terminal_status in (None, "completed")
    ):
        writeback_from_completed(enriched, settings=settings)
    if created:
        handle_fix_ingest_side_effects(state_root, enriched)
        processed = path.with_suffix(".json.processed")
        os.replace(path, processed)
    return stored_path, created


def ingest_inbox(state_root: Path, settings: Settings | None = None) -> list[dict]:
    inbox = ct104_inbox_dir(state_root)
    if not inbox.exists():
        return []
    results: list[dict] = []
    for path in sorted(inbox.glob("*.json")):
        if path.name.endswith(".processed"):
            continue
        stored, created = ingest_result_file(state_root, path, settings=settings)
        results.append({"path": str(path), "stored": str(stored), "created": created})
    return results
