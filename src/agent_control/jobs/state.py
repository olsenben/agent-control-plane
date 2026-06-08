"""State queue job: replay project event ledger and persist logical state."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_control.events import (
    clear_reduction_outbox,
    load_project_events,
    write_verification_state,
)
from agent_control.state_reducer import reduce_event_only


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

    return {
        "trigger_event_id": event_id,
        "project": project,
        "events_loaded": len(events),
        "state_path": str(state_path),
        "command_intent": state.command_intent,
        "snapshot_required": state.snapshot_required,
    }
