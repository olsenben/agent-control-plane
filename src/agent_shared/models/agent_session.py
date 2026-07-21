"""Typed agent session model (agent_session.v1) — CT103-authoritative."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from agent_shared.models.memory_preflight import SessionArtifactRef


class SessionStatus(str, Enum):
    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"
    BLOCKED = "blocked"


TERMINAL_STATUSES = frozenset(
    {
        SessionStatus.FINISHED,
        SessionStatus.FAILED,
        SessionStatus.BLOCKED,
    }
)

# Allowed nonterminal → next status (terminals handled separately).
_NONTERMINAL_TRANSITIONS: dict[SessionStatus, frozenset[SessionStatus]] = {
    SessionStatus.CREATED: frozenset(
        {
            SessionStatus.QUEUED,
            SessionStatus.RUNNING,
            SessionStatus.FAILED,
            SessionStatus.BLOCKED,
        }
    ),
    SessionStatus.QUEUED: frozenset(
        {
            SessionStatus.RUNNING,
            SessionStatus.FAILED,
            SessionStatus.BLOCKED,
        }
    ),
    SessionStatus.RUNNING: frozenset(
        {
            SessionStatus.RUNNING,
            SessionStatus.FINISHED,
            SessionStatus.FAILED,
            SessionStatus.BLOCKED,
        }
    ),
}

SubjectKind = Literal["issue", "pull_request"]
CommandKind = Literal["review", "plan", "fix", "repair"]


class AgentSession(BaseModel):
    """Durable CT103 session record.

    ``head_sha`` is the frozen dispatch-time source SHA (5.4a / 5.5a invariant).
    ``policy_source_sha`` is frozen at the same moment (empty string if unset).
    ``invoked_by`` is the human invoker (required). ``acting_identity`` is the bot
    principal (``agent-bot`` / ``GITEA_BOT_TOKEN``) — never the human invoker.
    """

    schema_version: str = "agent_session.v1"
    session_id: str
    project: str
    repo: str
    subject_kind: SubjectKind
    subject_number: int
    command_kind: CommandKind
    status: SessionStatus = SessionStatus.CREATED
    run_ids: list[str] = Field(default_factory=list)
    correlation_id: str
    trace_id: str | None = None
    input_state_sha: str
    head_sha: str
    policy_source_sha: str = ""
    risk_level: str
    risk_tags: list[str] = Field(default_factory=list)
    invoked_by: str
    invoked_by_id: int | None = None
    acting_identity: str | None = None
    approved_by: str | None = None
    source_comment_id: int | None = None
    source_delivery_id: str | None = None
    created_at: str
    updated_at: str
    finished_at: str | None = None
    terminal_reason_code: str | None = None
    terminal_reason: str | None = None
    memory_preflight: SessionArtifactRef | None = None
    context_packet: SessionArtifactRef | None = None
    recursive_context: SessionArtifactRef | None = None
    qwen_loop: SessionArtifactRef | None = None
    verification: SessionArtifactRef | None = None
    session_comment_id: int | None = None
    session_comment_version: int = 0
    last_rendered_event_sequence: int = 0
    last_rendered_status: str | None = None

    @model_validator(mode="after")
    def _session_id_distinct_from_runs(self) -> AgentSession:
        if self.session_id in self.run_ids:
            raise ValueError("session_id must be distinct from every run_id")
        if self.session_id.startswith("run-"):
            raise ValueError("session_id must not use run- prefix")
        for rid in self.run_ids:
            if not rid.startswith("run-"):
                raise ValueError(f"run_id must use run- prefix: {rid!r}")
        if not self.session_id.startswith("sess-"):
            raise ValueError("session_id must use sess- prefix")
        if not self.invoked_by:
            raise ValueError("invoked_by is required")
        return self


class SessionTransitionError(ValueError):
    """Illegal or conflicting session status transition."""


def apply_status_transition(
    session: AgentSession,
    *,
    new_status: SessionStatus,
    updated_at: str,
    terminal_reason_code: str | None = None,
    terminal_reason: str | None = None,
    finished_at: str | None = None,
) -> AgentSession:
    """Apply a status transition with terminal idempotency / conflict rules.

    - Same terminal status + same reason_code → no-op (return unchanged session).
    - Conflicting terminal → raise SessionTransitionError.
    - Nonterminal transitions must follow the allowed graph.
    """
    current = session.status
    if current in TERMINAL_STATUSES:
        if new_status == current:
            same_code = (session.terminal_reason_code or "") == (terminal_reason_code or "")
            if same_code:
                return session
            raise SessionTransitionError(
                f"conflicting terminal transition: {current.value} already set "
                f"(reason_code={session.terminal_reason_code!r} vs {terminal_reason_code!r})"
            )
        raise SessionTransitionError(
            f"session already terminal ({current.value}); cannot move to {new_status.value}"
        )

    if new_status in TERMINAL_STATUSES:
        return session.model_copy(
            update={
                "status": new_status,
                "updated_at": updated_at,
                "finished_at": finished_at or updated_at,
                "terminal_reason_code": terminal_reason_code,
                "terminal_reason": terminal_reason,
            }
        )

    allowed = _NONTERMINAL_TRANSITIONS.get(current, frozenset())
    if new_status not in allowed:
        raise SessionTransitionError(
            f"illegal transition {current.value} → {new_status.value}"
        )
    return session.model_copy(
        update={
            "status": new_status,
            "updated_at": updated_at,
        }
    )


def append_run_id(session: AgentSession, run_id: str, *, updated_at: str) -> AgentSession:
    """Append run_id with dedupe (retries must not duplicate)."""
    if run_id in session.run_ids:
        return session
    if run_id == session.session_id:
        raise ValueError("run_id must be distinct from session_id")
    if not run_id.startswith("run-"):
        raise ValueError(f"run_id must use run- prefix: {run_id!r}")
    return session.model_copy(
        update={
            "run_ids": [*session.run_ids, run_id],
            "updated_at": updated_at,
        }
    )


# --- Ledger event payloads ---


class SessionEventCorrelation(BaseModel):
    """CT103-derived fields required on mapped session ledger events."""

    schema_version: str = "agent_session_event.v1"
    session_id: str
    run_id: str
    repo: str
    project: str
    subject_kind: SubjectKind
    subject_number: int
    command_kind: CommandKind
    risk_level: str
    risk_tags: list[str] = Field(default_factory=list)
    input_state_sha: str
    head_sha: str
    correlation_id: str
    session_created_at: str
    event_at: str


class SessionStartedPayload(SessionEventCorrelation):
    status: SessionStatus = SessionStatus.QUEUED
    invoked_by: str
    invoked_by_id: int | None = None
    acting_identity: str | None = None
    approved_by: str | None = None
    source_comment_id: int | None = None
    source_delivery_id: str | None = None


class SubjectContextResolvedPayload(SessionEventCorrelation):
    """Webhook/subject context consumed at dispatch (not a live Gitea fetch)."""

    context_source: str = "webhook_trigger"


class SessionTerminalPayload(SessionEventCorrelation):
    status: SessionStatus
    terminal_at: str
    reason_code: str | None = None
    reason: str | None = None


class WorkerMappedPayload(SessionEventCorrelation):
    """Allowlisted worker contribution mapped onto CT103 correlation fields."""

    worker_event_kind: str
    outcome: str | None = None
    stage: str | None = None
    worker_timestamp: str | None = None
    evidence_digest: str | None = None
    error_classification: str | None = None
