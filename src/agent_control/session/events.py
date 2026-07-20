"""CT103 session ledger event builders."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_control.events import AgentEvent, append_event, deterministic_event_id
from agent_control.project_identity import canonical_project
from agent_shared.models.agent_session import (
    AgentSession,
    SessionStartedPayload,
    SessionStatus,
    SessionTerminalPayload,
    SubjectContextResolvedPayload,
    WorkerMappedPayload,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def correlation_payload(
    session: AgentSession,
    *,
    run_id: str,
    event_at: str | None = None,
) -> dict[str, Any]:
    """CT103-derived correlation fields — never trust worker JSONL for these."""
    at = event_at or _now()
    return {
        "schema_version": "agent_session_event.v1",
        "session_id": session.session_id,
        "run_id": run_id,
        "repo": session.repo,
        "project": session.project,
        "subject_kind": session.subject_kind,
        "subject_number": session.subject_number,
        "command_kind": session.command_kind,
        "risk_level": session.risk_level,
        "risk_tags": list(session.risk_tags),
        "input_state_sha": session.input_state_sha,
        "head_sha": session.head_sha,
        "correlation_id": session.correlation_id,
        "session_created_at": session.created_at,
        "event_at": at,
    }


def append_session_event(
    state_root: Path,
    *,
    event_type: str,
    session: AgentSession,
    run_id: str,
    payload: dict[str, Any],
    delivery_suffix: str = "",
) -> tuple[Path, bool]:
    delivery = f"{session.session_id}:{run_id}:{event_type}"
    if delivery_suffix:
        delivery = f"{delivery}:{delivery_suffix}"
    event_id = deterministic_event_id("ct103", delivery, event_type)
    event = AgentEvent(
        event_id=event_id,
        type=event_type,
        raw_event_type=event_type,
        source="ct103",
        delivery_id=delivery,
        project=canonical_project(session.project),
        payload=payload,
        recorded_at=_now(),
    )
    return append_event(state_root, event)


def append_session_started(
    state_root: Path,
    session: AgentSession,
    *,
    run_id: str,
) -> tuple[Path, bool]:
    at = _now()
    body = SessionStartedPayload(
        **correlation_payload(session, run_id=run_id, event_at=at),
        status=SessionStatus.QUEUED,
        invoked_by=session.invoked_by,
    )
    return append_session_event(
        state_root,
        event_type="agent.session_started",
        session=session,
        run_id=run_id,
        payload=body.model_dump(mode="json"),
    )


def append_subject_context_resolved(
    state_root: Path,
    session: AgentSession,
    *,
    run_id: str,
) -> tuple[Path, bool]:
    at = _now()
    body = SubjectContextResolvedPayload(
        **correlation_payload(session, run_id=run_id, event_at=at),
        context_source="webhook_trigger",
    )
    return append_session_event(
        state_root,
        event_type="agent.subject_context_resolved",
        session=session,
        run_id=run_id,
        payload=body.model_dump(mode="json"),
    )


def append_session_terminal(
    state_root: Path,
    session: AgentSession,
    *,
    run_id: str,
    event_type: str,
    reason_code: str | None = None,
    reason: str | None = None,
) -> tuple[Path, bool]:
    at = session.finished_at or _now()
    body = SessionTerminalPayload(
        **correlation_payload(session, run_id=run_id, event_at=at),
        status=session.status,
        terminal_at=at,
        reason_code=reason_code or session.terminal_reason_code,
        reason=reason or session.terminal_reason,
    )
    return append_session_event(
        state_root,
        event_type=event_type,
        session=session,
        run_id=run_id,
        payload=body.model_dump(mode="json"),
    )


def append_session_finished(
    state_root: Path,
    session: AgentSession,
    *,
    run_id: str,
) -> tuple[Path, bool]:
    return append_session_terminal(
        state_root,
        session,
        run_id=run_id,
        event_type="agent.session_finished",
    )


def append_session_failed(
    state_root: Path,
    session: AgentSession,
    *,
    run_id: str,
    reason_code: str,
    reason: str | None = None,
) -> tuple[Path, bool]:
    return append_session_terminal(
        state_root,
        session,
        run_id=run_id,
        event_type="agent.session_failed",
        reason_code=reason_code,
        reason=reason,
    )


def append_session_blocked(
    state_root: Path,
    session: AgentSession,
    *,
    run_id: str,
    reason_code: str,
    reason: str | None = None,
) -> tuple[Path, bool]:
    return append_session_terminal(
        state_root,
        session,
        run_id=run_id,
        event_type="agent.session_blocked",
        reason_code=reason_code,
        reason=reason,
    )


def append_worker_mapped_event(
    state_root: Path,
    session: AgentSession,
    *,
    run_id: str,
    worker_event_kind: str,
    outcome: str | None = None,
    stage: str | None = None,
    worker_timestamp: str | None = None,
    evidence_digest: str | None = None,
    error_classification: str | None = None,
) -> tuple[Path, bool]:
    at = _now()
    body = WorkerMappedPayload(
        **correlation_payload(session, run_id=run_id, event_at=at),
        worker_event_kind=worker_event_kind,
        outcome=outcome,
        stage=stage,
        worker_timestamp=worker_timestamp,
        evidence_digest=evidence_digest,
        error_classification=error_classification,
    )
    return append_session_event(
        state_root,
        event_type="agent.session_worker_event",
        session=session,
        run_id=run_id,
        payload=body.model_dump(mode="json"),
        delivery_suffix=worker_event_kind,
    )


def append_memory_preflight_created(
    state_root: Path,
    session: AgentSession,
    *,
    run_id: str,
    digest: str,
    status: str,
    recursive_context_required: bool,
    relative_path: str,
) -> tuple[Path, bool]:
    at = _now()
    payload = {
        **correlation_payload(session, run_id=run_id, event_at=at),
        "artifact_digest": digest,
        "preflight_status": status,
        "recursive_context_required": recursive_context_required,
        "relative_path": relative_path,
        "schema": "memory_preflight.v1",
    }
    return append_session_event(
        state_root,
        event_type="agent.memory_preflight_created",
        session=session,
        run_id=run_id,
        payload=payload,
    )


def append_memory_preflight_failed(
    state_root: Path,
    session: AgentSession,
    *,
    run_id: str,
    reason: str,
    reason_code: str = "preflight_persist_failed",
) -> tuple[Path, bool]:
    at = _now()
    payload = {
        **correlation_payload(session, run_id=run_id, event_at=at),
        "reason_code": reason_code,
        "reason": reason,
    }
    return append_session_event(
        state_root,
        event_type="agent.memory_preflight_failed",
        session=session,
        run_id=run_id,
        payload=payload,
    )


def append_context_packet_created(
    state_root: Path,
    session: AgentSession,
    *,
    run_id: str,
    digest: str,
    preflight_digest: str,
    context_pack_digest: str,
    relative_path: str,
) -> tuple[Path, bool]:
    at = _now()
    payload = {
        **correlation_payload(session, run_id=run_id, event_at=at),
        "artifact_digest": digest,
        "preflight_digest": preflight_digest,
        "context_pack_digest": context_pack_digest,
        "relative_path": relative_path,
        "schema": "context_packet.v1",
    }
    return append_session_event(
        state_root,
        event_type="agent.context_packet_created",
        session=session,
        run_id=run_id,
        payload=payload,
    )
