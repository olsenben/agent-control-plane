"""State queue job: replay project event ledger and persist logical state."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_control.approval.handlers import handle_approval_commands
from agent_control.config import get_settings
from agent_control.events import (
    clear_reduction_outbox,
    load_project_events,
    write_verification_state,
)
from agent_control.state_reducer import dispatch_for_event, reduce_event_only
from agent_control.workflows.dispatch import maybe_dispatch_rlm_root


def process_state_reduction(state_root: str, event_id: str, project: str) -> dict[str, Any]:
    """Replay all ledger events for project; write verification_state.json."""
    root = Path(state_root)
    events = load_project_events(root, project)
    state = reduce_event_only(events, project)

    if events:
        last = events[-1]
        state.last_event_id = last.get("event_id")
        state.last_event_type = last.get("type")
    state.event_count = len(events)
    state.last_reduced_at = datetime.now(timezone.utc).isoformat()

    state_path = write_verification_state(root, project, state)
    clear_reduction_outbox(root, event_id)

    dispatch_result: dict[str, Any] = {"dispatched": False}
    approval_result: dict[str, Any] = {"handled": False}
    if events:
        trigger = next((e for e in reversed(events) if e.get("event_id") == event_id), events[-1])
        trigger_intent, trigger_dispatch, trigger_kind = dispatch_for_event(trigger)
        settings = get_settings()

        if trigger_intent.activated and trigger_intent.kind in ("approve", "reject", "fix"):
            approval_result = handle_approval_commands(
                root,
                project,
                trigger,
                trigger_intent,
                settings=settings,
            )
        elif trigger_dispatch:
            dispatch_state = state.model_copy(
                update={
                    "command_intent": trigger_intent,
                    "dispatch_recommended": True,
                    "dispatch_kind": trigger_kind,
                }
            )
            try:
                dispatch_result = maybe_dispatch_rlm_root(
                    dispatch_state,
                    trigger,
                    settings.redis_url,
                    settings=settings,
                )
            except Exception as exc:
                dispatch_result = {"dispatched": False, "error": str(exc)}

    intent = state.command_intent
    return {
        "trigger_event_id": event_id,
        "project": project,
        "events_loaded": len(events),
        "state_path": str(state_path),
        "command_intent": intent.kind if intent else None,
        "dispatch_recommended": state.dispatch_recommended,
        "snapshot_required": state.snapshot_required,
        "dispatch": dispatch_result,
        "approval": approval_result,
    }
