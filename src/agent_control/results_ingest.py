"""Ingest CT104 result events into the CT103 event ledger."""

from __future__ import annotations

import json
import os
from pathlib import Path

from agent_control.config import Settings, get_settings
from agent_control.events import AgentEvent, append_event, deterministic_event_id
from agent_control.memory.mapper import policy_gate_risk_tags
from agent_control.memory.writeback import writeback_from_completed
from agent_shared.models.events import AgentRunCompletedEvent, RiskTagSourceEntry


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
    writeback_from_completed(enriched, settings=settings)
    if created:
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
