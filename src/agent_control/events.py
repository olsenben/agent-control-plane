"""Normalized agent events and deterministic IDs."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def deterministic_event_id(source: str, delivery_id: str, event_type: str) -> str:
    """Stable event ID from delivery metadata."""
    payload = f"{source}:{delivery_id}:{event_type}"
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def event_storage_path(
    state_root: Path,
    owner: str,
    repo: str,
    event_id: str,
    when: datetime | None = None,
) -> Path:
    """Path: projects/{owner}/{repo}/events/YYYY/MM/DD/{event_id}.json"""
    ts = when or datetime.now(timezone.utc)
    return (
        state_root
        / "projects"
        / owner
        / repo
        / "events"
        / f"{ts.year:04d}"
        / f"{ts.month:02d}"
        / f"{ts.day:02d}"
        / f"{event_id}.json"
    )


class AgentEvent(BaseModel):
    model_config = ConfigDict(populate_by_name=True, protected_namespaces=())

    schema_name: str = Field(default="agent.event.v1", serialization_alias="schema", alias="schema")
    event_id: str
    type: str
    source: str = "gitea.webhook"
    delivery_id: str | None = None
    project: str
    payload: dict[str, Any] = Field(default_factory=dict)
    recorded_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )

def append_event(state_root: Path, event: AgentEvent) -> Path:
    """Append event JSON; skip if file already exists (dedupe)."""
    owner, repo = event.project.split("/", 1)
    path = event_storage_path(state_root, owner, repo, event.event_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path
    path.write_text(
        json.dumps(event.model_dump(by_alias=True, mode="json"), indent=2),
        encoding="utf-8",
    )
    return path
