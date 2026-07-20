"""Ingest CT104 result events into the CT103 event ledger.

``agent.run_completed`` means the run reached a terminal state, not that the agent succeeded.
Failed runs use ``status=failed`` with a ``terminal_status`` of ``failed_*``.

V4.1.1: worker-reported ``pr_opened_pending_ci`` is non-authoritative. Publication is
enqueued only for ``producer_protocol=patch-bundle.v1`` + ``patch_bundle_ready``.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from agent_control.config import Settings, get_settings
from agent_control.events import AgentEvent, append_event, deterministic_event_id
from agent_control.gitea_comments import post_issue_comment
from agent_control.memory.mapper import policy_gate_risk_tags
from agent_control.memory.writeback import writeback_from_completed
from agent_shared.constants import (
    FIX_STATUS_PATCH_BUNDLE_READY,
    PRODUCER_PROTOCOL_PATCH_BUNDLE_V1,
)
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


def _maybe_enqueue_publish(
    state_root: Path,
    event: AgentRunCompletedEvent,
    settings: Settings,
) -> None:
    from agent_control.publish.state import try_enqueue_cas
    from agent_control.queue import enqueue_publish

    if event.command_kind != "fix":
        return
    if event.producer_protocol != PRODUCER_PROTOCOL_PATCH_BUNDLE_V1:
        return
    if event.fix_status not in (FIX_STATUS_PATCH_BUNDLE_READY, "local_patch_passed"):
        # local_patch_passed without protocol is legacy — ignore for brokerage
        if event.fix_status != FIX_STATUS_PATCH_BUNDLE_READY:
            return
    if not event.bundle_id:
        return
    if not settings.fix_remote_publish_enabled:
        return

    attempt_id = event.attempt_id or "1"
    kind = event.bundle_kind or "fix"
    record = try_enqueue_cas(
        state_root,
        run_id=event.run_id,
        kind=kind,
        attempt_id=attempt_id,
        bundle_id=event.bundle_id,
        project=event.project,
        approval_id=event.approval_id,
        approval_target_id=event.approval_target_id,
    )
    if record is None:
        return  # already queued / terminal

    enqueue_publish(
        settings.redis_url,
        run_id=event.run_id,
        kind=kind,
        attempt_id=attempt_id,
        bundle_id=event.bundle_id,
        state_root=str(state_root),
    )

    if event.project and event.issue_id is not None:
        try:
            post_issue_comment(
                event.project,
                event.issue_id,
                (
                    "## Local patch queued\n\n"
                    "Local patch produced and queued for independent publication validation.\n\n"
                    f"- Run: `{event.run_id}`\n"
                    f"- Bundle: `{event.bundle_id}`\n"
                ),
                settings=settings,
            )
        except Exception:
            pass


# Risk 0/1 run comments formerly posted by CT104 worker-report.
_RUN_COMMENT_KINDS = frozenset({"inspect", "explain", "review", "plan"})


def _maybe_post_run_comment(
    event: AgentRunCompletedEvent,
    settings: Settings,
) -> None:
    """Post plan/review/inspect/explain (and failed-fix) summaries via CT103 bot token.

    Successful fix bundles are covered by publish-queue / publish-broker comments.
    """
    if event.project is None or event.issue_id is None:
        return
    summary = (event.summary or "").strip()
    if not summary:
        return

    kind = event.command_kind or ""
    if kind in _RUN_COMMENT_KINDS:
        pass
    elif kind == "fix" and event.status == "failed":
        pass
    else:
        return

    try:
        post_issue_comment(event.project, event.issue_id, summary, settings=settings)
    except Exception:
        pass


def handle_fix_ingest_side_effects(
    state_root: Path,
    event: AgentRunCompletedEvent,
    settings: Settings | None = None,
) -> None:
    """Enqueue CT103 brokerage for patch bundles; release approval on worker failure.

    Does **not** consume approval or register pending CI from worker-reported
    ``pr_opened_pending_ci`` (non-authoritative after V4.1.1).
    """
    settings = settings or get_settings()

    # Ignore legacy worker-claimed publish success
    if event.fix_status == "pr_opened_pending_ci" and event.producer_protocol != PRODUCER_PROTOCOL_PATCH_BUNDLE_V1:
        return

    _maybe_post_run_comment(event, settings)
    _maybe_enqueue_publish(state_root, event, settings)

    if event.command_kind != "fix" or not event.approval_id or not event.approval_target_id:
        return
    if event.project is None or event.issue_id is None:
        return

    from agent_control.approval.events import append_approval_released
    from agent_control.approval.service import release_approval_reservation
    from agent_control.approval.storage import load_approval
    from agent_shared.models.approval import ApprovalReleasedEvent

    approval = load_approval(state_root, event.project, event.approval_target_id)
    if approval is None:
        return

    if event.status == "failed" and approval.status == "reserved":
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
    from agent_control.session import SessionMismatchError, handle_ingest_session_update
    from agent_control.session.lifecycle import resolve_session_for_ingest

    # Fail closed on session identity mismatch before ledger append / finalize.
    try:
        resolve_session_for_ingest(state_root, event_model)
    except LookupError:
        pass  # inspect/explain and other non-typed runs
    except SessionMismatchError:
        # Do not append mapped session events or finalize; leave inbox for ops.
        raise

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
        from agent_control.memory.session_writeback import should_defer_ingest_writeback

        if not should_defer_ingest_writeback(state_root, event_model):
            writeback_from_completed(enriched, settings=settings)
    if created:
        try:
            handle_ingest_session_update(state_root, enriched)
        except LookupError:
            pass
        handle_fix_ingest_side_effects(state_root, enriched, settings=settings)
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
