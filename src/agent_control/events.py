"""Normalized agent events and deterministic IDs."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agent_shared.models.state import VerificationState

LogicalState = VerificationState


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


def project_summaries_dir(state_root: Path, project: str) -> Path:
    owner, repo = project.split("/", 1)
    return state_root / "projects" / owner / repo / "summaries"


def reduction_outbox_path(state_root: Path, event_id: str) -> Path:
    return state_root / "outbox" / "state" / f"{event_id}.json"


class AgentEvent(BaseModel):
    model_config = ConfigDict(populate_by_name=True, protected_namespaces=())

    schema_name: str = Field(default="agent.event.v1", serialization_alias="schema", alias="schema")
    event_id: str
    type: str
    raw_event_type: str = ""
    raw_action: str | None = None
    source: str = "gitea.webhook"
    delivery_id: str | None = None
    project: str
    payload: dict[str, Any] = Field(default_factory=dict)
    recorded_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )


def append_event(state_root: Path, event: AgentEvent) -> tuple[Path, bool]:
    """Append event JSON atomically; return (path, created)."""
    owner, repo = event.project.split("/", 1)
    path = event_storage_path(state_root, owner, repo, event.event_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path, False

    body = json.dumps(event.model_dump(by_alias=True, mode="json"), indent=2)
    tmp = path.with_suffix(".json.tmp")
    try:
        with open(tmp, "x", encoding="utf-8") as handle:
            handle.write(body)
        os.replace(tmp, path)
        return path, True
    finally:
        if tmp.exists() and not path.exists():
            tmp.unlink(missing_ok=True)


def load_project_events(state_root: Path, project: str) -> list[dict[str, Any]]:
    """Load all event JSON files for a project, stable-sorted."""
    owner, repo = project.split("/", 1)
    events_dir = state_root / "projects" / owner / repo / "events"
    if not events_dir.exists():
        return []

    loaded: list[tuple[str, str, str, dict[str, Any]]] = []
    for path in events_dir.rglob("*.json"):
        if path.name.endswith(".tmp"):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        recorded_at = data.get("recorded_at", "")
        event_id = data.get("event_id", "")
        loaded.append((recorded_at, event_id, str(path), data))

    loaded.sort(key=lambda item: (item[0], item[1], item[2]))
    return [item[3] for item in loaded]


def write_verification_state(state_root: Path, project: str, state: LogicalState) -> Path:
    """Atomically write summaries/verification_state.json."""
    summaries = project_summaries_dir(state_root, project)
    summaries.mkdir(parents=True, exist_ok=True)
    final_path = summaries / "verification_state.json"
    tmp_path = final_path.with_suffix(".json.tmp")
    body = state.model_dump_json(indent=2)
    tmp_path.write_text(body, encoding="utf-8")
    os.replace(tmp_path, final_path)
    return final_path


def write_reduction_outbox(state_root: Path, event_id: str, project: str) -> Path:
    """Record a pending state reduction when Redis enqueue fails."""
    path = reduction_outbox_path(state_root, event_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    marker = {
        "event_id": event_id,
        "project": project,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(marker, indent=2), encoding="utf-8")
    return path


def clear_reduction_outbox(state_root: Path, event_id: str) -> None:
    path = reduction_outbox_path(state_root, event_id)
    path.unlink(missing_ok=True)


def list_reduction_outbox(state_root: Path, project: str | None = None) -> list[dict[str, Any]]:
    outbox_dir = state_root / "outbox" / "state"
    if not outbox_dir.exists():
        return []
    markers: list[dict[str, Any]] = []
    for path in sorted(outbox_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if project is None or data.get("project") == project:
            markers.append(data)
    return markers
