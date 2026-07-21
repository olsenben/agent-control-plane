"""Invocation lifecycle storage + FSM transitions (V6 T07)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from agent_control.project_identity import canonical_project
from agent_shared.models.invocation import AgentIntent, InvocationRecord, InvocationStatus


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_invocation_id() -> str:
    return f"inv-{uuid.uuid4().hex[:16]}"


def _path(state_root: Path, project: str, invocation_id: str) -> Path:
    owner, repo = canonical_project(project).split("/", 1)
    return state_root / "projects" / owner / repo / "invocations" / f"{invocation_id}.json"


def save_invocation(state_root: Path, record: InvocationRecord) -> Path:
    path = _path(state_root, record.project, record.invocation_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_invocation(state_root: Path, project: str, invocation_id: str) -> InvocationRecord | None:
    path = _path(state_root, project, invocation_id)
    if not path.is_file():
        return None
    return InvocationRecord.model_validate_json(path.read_text(encoding="utf-8"))


def begin_invocation(
    state_root: Path,
    *,
    project: str,
    raw_text: str,
    invoked_by: str = "unknown",
    source_comment_id: int | None = None,
    source_delivery_id: str | None = None,
    subject_number: int | None = None,
    intent: AgentIntent | None = None,
) -> InvocationRecord:
    now = _now()
    status: InvocationStatus = "invocation_received"
    if intent is not None:
        if intent.kind and intent.confidence >= 0.7:
            status = "intent_resolved"
        else:
            status = "intent_ambiguous"
    record = InvocationRecord(
        invocation_id=make_invocation_id(),
        project=canonical_project(project),
        status=status,
        source_comment_id=source_comment_id,
        source_delivery_id=source_delivery_id,
        subject_number=subject_number,
        invoked_by=invoked_by,
        raw_text=raw_text,
        intent=intent,
        created_at=now,
        updated_at=now,
    )
    save_invocation(state_root, record)
    return record


def transition_invocation(
    state_root: Path,
    record: InvocationRecord,
    *,
    status: InvocationStatus,
    intent: AgentIntent | None = None,
    session_id: str | None = None,
    run_id: str | None = None,
) -> InvocationRecord:
    updates: dict = {"status": status, "updated_at": _now()}
    if intent is not None:
        updates["intent"] = intent
    if session_id is not None:
        updates["session_id"] = session_id
    if run_id is not None:
        updates["run_id"] = run_id
    updated = record.model_copy(update=updates)
    save_invocation(state_root, updated)
    return updated


def request_clarification(state_root: Path, record: InvocationRecord) -> InvocationRecord:
    return transition_invocation(state_root, record, status="clarification_requested")


def mark_session_created(
    state_root: Path,
    record: InvocationRecord,
    *,
    session_id: str,
    run_id: str,
) -> InvocationRecord:
    return transition_invocation(
        state_root,
        record,
        status="session_created",
        session_id=session_id,
        run_id=run_id,
    )


def list_invocations(state_root: Path, project: str) -> list[InvocationRecord]:
    owner, repo = canonical_project(project).split("/", 1)
    root = state_root / "projects" / owner / repo / "invocations"
    if not root.is_dir():
        return []
    out: list[InvocationRecord] = []
    for path in sorted(root.glob("inv-*.json")):
        try:
            out.append(InvocationRecord.model_validate(json.loads(path.read_text(encoding="utf-8"))))
        except Exception:
            continue
    return out
