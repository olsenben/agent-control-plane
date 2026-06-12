"""Ingest CT104 result events into the CT103 event ledger."""

from __future__ import annotations

import json
import os
from pathlib import Path

from agent_control.events import AgentEvent, append_event, deterministic_event_id
from agent_shared.models.events import AgentRunCompletedEvent


def ct104_inbox_dir(state_root: Path) -> Path:
    return state_root / "inbox" / "ct104-results"


def ingest_result_file(state_root: Path, path: Path) -> tuple[Path, bool]:
    data = json.loads(path.read_text(encoding="utf-8"))
    event_model = AgentRunCompletedEvent.model_validate(data)
    event_id = deterministic_event_id(
        "ct104",
        event_model.run_id,
        "agent.run_completed",
    )
    event = AgentEvent(
        event_id=event_id,
        type="agent.run_completed",
        raw_event_type="agent.run_completed",
        source="ct104",
        delivery_id=event_model.run_id,
        project=event_model.project,
        payload=event_model.model_dump(mode="json"),
    )
    stored_path, created = append_event(state_root, event)
    if created:
        processed = path.with_suffix(".json.processed")
        os.replace(path, processed)
    return stored_path, created


def ingest_inbox(state_root: Path) -> list[dict]:
    inbox = ct104_inbox_dir(state_root)
    if not inbox.exists():
        return []
    results: list[dict] = []
    for path in sorted(inbox.glob("*.json")):
        if path.name.endswith(".processed"):
            continue
        stored, created = ingest_result_file(state_root, path)
        results.append({"path": str(path), "stored": str(stored), "created": created})
    return results
