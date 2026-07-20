"""Session lifecycle: create at dispatch, finalize by terminal owner."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from agent_control.session.events import (
    append_session_blocked,
    append_session_failed,
    append_session_finished,
    append_session_started,
    append_subject_context_resolved,
    append_worker_mapped_event,
)
from agent_control.session.storage import (
    SessionStoreError,
    load_session_by_run,
    lookup_session_id_by_run,
    persist_session_with_run_index,
    save_run_index,
    save_session,
)
from agent_shared.input_state import (
    compute_input_state_sha,
    default_risk_tags,
    make_correlation_id,
    make_session_id,
    risk_level_for_command,
)
from agent_shared.models.agent_session import (
    AgentSession,
    CommandKind,
    SessionStatus,
    SessionTransitionError,
    SubjectKind,
    append_run_id,
    apply_status_transition,
)
from agent_shared.models.events import AgentRunCompletedEvent
from agent_shared.project_ids import split_project
from agent_shared.repo_identity import normalize_repo_full_name

logger = logging.getLogger(__name__)

TYPED_SESSION_COMMANDS = frozenset({"review", "plan", "fix", "repair"})

# Commands whose successful terminal is results-ingest (not publish).
INGEST_TERMINAL_OWNERS = frozenset({"review", "plan"})

# Commands that stay nonterminal through worker ingest; publish/verify owns finish.
PUBLISH_TERMINAL_OWNERS = frozenset({"fix", "repair"})

# Tiny allowlist: worker may contribute only these event kinds (mapped, nonterminal).
WORKER_EVENT_ALLOWLIST = frozenset(
    {
        "worker_execution_started",
        "worker_result_produced",
        "worker_execution_failed",
        "verification_result_available",
    }
)


class SessionMismatchError(ValueError):
    """Worker-supplied session_id/run_id does not match CT103 store."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _subject_from_trigger(
    trigger_context: Any,
    *,
    command_kind: str,
) -> tuple[SubjectKind, int]:
    pr = getattr(trigger_context, "pr_number", None)
    issue = getattr(trigger_context, "issue_number", None)
    if isinstance(trigger_context, dict):
        pr = trigger_context.get("pr_number")
        issue = trigger_context.get("issue_number")
    if pr is not None:
        return "pull_request", int(pr)
    if issue is not None:
        return "issue", int(issue)
    # Repair / fix without numbers should not happen for typed sessions.
    raise ValueError(f"missing subject number for {command_kind}")


def _invoked_by_from_trigger(trigger_context: Any) -> str:
    if isinstance(trigger_context, dict):
        author = trigger_context.get("author")
    else:
        author = getattr(trigger_context, "author", None)
    return str(author or "unknown")


def create_session_record(
    *,
    project: str,
    command_kind: CommandKind,
    run_id: str,
    head_sha: str,
    trigger_context: Any,
    policy_source_sha: str = "",
    risk_tags: list[str] | None = None,
    session_id: str | None = None,
) -> AgentSession:
    """Build a new agent_session.v1 (not yet persisted)."""
    if command_kind not in TYPED_SESSION_COMMANDS:
        raise ValueError(f"typed sessions not used for command_kind={command_kind}")
    if not run_id.startswith("run-"):
        raise ValueError(f"run_id must use run- prefix: {run_id!r}")

    sid = session_id or make_session_id()
    if sid == run_id or sid.startswith("run-"):
        raise ValueError("session_id must be distinct from run_id")

    subject_kind, subject_number = _subject_from_trigger(
        trigger_context, command_kind=command_kind
    )
    _, repo = split_project(project)
    repo_full = normalize_repo_full_name(project) or project
    input_sha = compute_input_state_sha(
        project=repo_full,
        subject_kind=subject_kind,
        subject_number=subject_number,
        command_kind=command_kind,
        head_sha=head_sha or "",
        policy_source_sha=policy_source_sha or "",
    )
    now = _now()
    tags = list(risk_tags) if risk_tags is not None else default_risk_tags(command_kind)
    return AgentSession(
        session_id=sid,
        project=repo_full,
        repo=repo,
        subject_kind=subject_kind,
        subject_number=subject_number,
        command_kind=command_kind,
        status=SessionStatus.CREATED,
        run_ids=[run_id],
        correlation_id=make_correlation_id(session_id=sid, run_id=run_id),
        input_state_sha=input_sha,
        head_sha=head_sha or "",
        risk_level=risk_level_for_command(command_kind),
        risk_tags=tags,
        invoked_by=_invoked_by_from_trigger(trigger_context),
        acting_identity=None,
        created_at=now,
        updated_at=now,
    )


def begin_typed_session(
    state_root: Path,
    *,
    project: str,
    command_kind: CommandKind,
    run_id: str,
    head_sha: str,
    trigger_context: Any,
    policy_source_sha: str = "",
    risk_tags: list[str] | None = None,
) -> AgentSession:
    """Persist session + index + session_started + subject_context_resolved.

    Failures raise SessionStoreError / propagate ledger errors — caller must not enqueue.
    Idempotent when run_id already indexed (returns existing session).
    """
    existing = load_session_by_run(state_root, project, run_id)
    if existing is not None:
        return existing

    session = create_session_record(
        project=project,
        command_kind=command_kind,
        run_id=run_id,
        head_sha=head_sha,
        trigger_context=trigger_context,
        policy_source_sha=policy_source_sha,
        risk_tags=risk_tags,
    )
    session = apply_status_transition(
        session,
        new_status=SessionStatus.QUEUED,
        updated_at=_now(),
    )
    persist_session_with_run_index(state_root, session)
    started_path, _ = append_session_started(state_root, session, run_id=run_id)
    if not started_path:
        raise SessionStoreError("failed to append agent.session_started")
    append_subject_context_resolved(state_root, session, run_id=run_id)
    return session


def append_run_to_session(
    state_root: Path,
    session: AgentSession,
    *,
    run_id: str,
) -> AgentSession:
    """Bind another run_id to an existing session (retry / auto-repair)."""
    bound = lookup_session_id_by_run(state_root, session.project, run_id)
    if bound and bound != session.session_id:
        raise SessionStoreError(
            f"run_id {run_id} already bound to {bound}, not {session.session_id}"
        )
    updated = append_run_id(session, run_id, updated_at=_now())
    save_session(state_root, updated)
    save_run_index(
        state_root,
        project=updated.project,
        run_id=run_id,
        session_id=updated.session_id,
    )
    return updated


def mark_session_running(state_root: Path, session: AgentSession) -> AgentSession:
    if session.status in (
        SessionStatus.FINISHED,
        SessionStatus.FAILED,
        SessionStatus.BLOCKED,
    ):
        return session
    updated = apply_status_transition(
        session,
        new_status=SessionStatus.RUNNING,
        updated_at=_now(),
    )
    save_session(state_root, updated)
    return updated


def finalize_session(
    state_root: Path,
    session: AgentSession,
    *,
    run_id: str,
    status: Literal["finished", "failed", "blocked"],
    reason_code: str | None = None,
    reason: str | None = None,
) -> AgentSession:
    """Terminal transition + ledger event. Idempotent for same terminal+reason."""
    status_enum = {
        "finished": SessionStatus.FINISHED,
        "failed": SessionStatus.FAILED,
        "blocked": SessionStatus.BLOCKED,
    }[status]
    try:
        updated = apply_status_transition(
            session,
            new_status=status_enum,
            updated_at=_now(),
            terminal_reason_code=reason_code,
            terminal_reason=reason,
        )
    except SessionTransitionError:
        logger.exception(
            "session_terminal_conflict session_id=%s run_id=%s wanted=%s",
            session.session_id,
            run_id,
            status,
        )
        raise

    if updated is session and session.status == status_enum:
        # no-op idempotent
        return session

    save_session(state_root, updated)
    if status == "finished":
        append_session_finished(state_root, updated, run_id=run_id)
    elif status == "failed":
        append_session_failed(
            state_root,
            updated,
            run_id=run_id,
            reason_code=reason_code or "session_failed",
            reason=reason,
        )
    else:
        append_session_blocked(
            state_root,
            updated,
            run_id=run_id,
            reason_code=reason_code or "session_blocked",
            reason=reason,
        )
    return updated


def finalize_enqueue_failure(
    state_root: Path,
    session: AgentSession,
    *,
    run_id: str,
    reason: str = "enqueue_failed",
) -> AgentSession:
    return finalize_session(
        state_root,
        session,
        run_id=run_id,
        status="failed",
        reason_code="enqueue_failed",
        reason=reason,
    )


def resolve_session_for_ingest(
    state_root: Path,
    event: AgentRunCompletedEvent,
) -> AgentSession:
    """Load CT103 session for ingest; fail closed on session_id/run_id mismatch."""
    project = event.project or event.repo_full_name or ""
    if not project:
        raise SessionMismatchError("missing project on run completed event")

    stored = load_session_by_run(state_root, project, event.run_id)
    if stored is None:
        # Non-typed commands (inspect/explain) have no session — caller skips.
        worker_sid = event.session_id
        if worker_sid and worker_sid != event.run_id and worker_sid.startswith("sess-"):
            raise SessionMismatchError(
                f"worker session_id {worker_sid} has no CT103 run index for {event.run_id}"
            )
        raise LookupError(f"no session for run_id={event.run_id}")

    worker_sid = event.session_id
    if worker_sid and worker_sid != stored.session_id:
        raise SessionMismatchError(
            f"worker session_id {worker_sid} != CT103 {stored.session_id}"
        )
    if event.run_id not in stored.run_ids:
        raise SessionMismatchError(
            f"run_id {event.run_id} not in session {stored.session_id} run_ids"
        )
    return stored


def map_worker_allowlisted_events(
    state_root: Path,
    session: AgentSession,
    *,
    run_id: str,
    event: AgentRunCompletedEvent,
) -> list[str]:
    """Emit allowlisted nonterminal mapped events derived from run outcome."""
    emitted: list[str] = []
    # Synthetic allowlist mapping from run_completed (worker jsonl mapping later).
    kind = "worker_result_produced"
    if event.status == "failed":
        kind = "worker_execution_failed"
    if kind not in WORKER_EVENT_ALLOWLIST:
        return emitted
    append_worker_mapped_event(
        state_root,
        session,
        run_id=run_id,
        worker_event_kind=kind,
        outcome=event.status,
        stage="results_ingest",
        evidence_digest=event.summary_hash,
        error_classification=event.terminal_status if event.status == "failed" else None,
    )
    emitted.append(kind)
    return emitted


def handle_ingest_session_update(
    state_root: Path,
    event: AgentRunCompletedEvent,
) -> dict[str, Any]:
    """Apply ingest-time session rules. Returns action summary.

    - Mismatch → raise SessionMismatchError (caller must not finalize / map).
    - review/plan → terminal finished|failed.
    - fix/repair → running update only (publish owns terminal).
    """
    try:
        session = resolve_session_for_ingest(state_root, event)
    except LookupError:
        return {"skipped": True, "reason": "no_typed_session"}

    map_worker_allowlisted_events(
        state_root, session, run_id=event.run_id, event=event
    )

    kind = session.command_kind
    if kind in PUBLISH_TERMINAL_OWNERS:
        updated = mark_session_running(state_root, session)
        return {
            "skipped": False,
            "session_id": updated.session_id,
            "status": updated.status.value,
            "terminal": False,
        }

    if kind in INGEST_TERMINAL_OWNERS:
        success = event.status == "completed" and event.terminal_status in (
            None,
            "completed",
        )
        if success:
            updated = finalize_session(
                state_root,
                session,
                run_id=event.run_id,
                status="finished",
                reason_code="ingest_completed",
                reason="validated result persisted",
            )
        else:
            updated = finalize_session(
                state_root,
                session,
                run_id=event.run_id,
                status="failed",
                reason_code=event.terminal_status or "worker_failed",
                reason=event.summary[:500] if event.summary else "worker failed",
            )
        return {
            "skipped": False,
            "session_id": updated.session_id,
            "status": updated.status.value,
            "terminal": True,
        }

    return {"skipped": True, "reason": f"unhandled_command_kind:{kind}"}


def handle_publish_session_terminal(
    state_root: Path,
    *,
    project: str,
    run_id: str,
    success: bool,
    reason_code: str | None = None,
    reason: str | None = None,
) -> AgentSession | None:
    """Fix/repair terminal owner — publish/verification path."""
    session = load_session_by_run(state_root, project, run_id)
    if session is None:
        return None
    if session.command_kind not in PUBLISH_TERMINAL_OWNERS:
        return session
    if success:
        return finalize_session(
            state_root,
            session,
            run_id=run_id,
            status="finished",
            reason_code=reason_code or "publish_succeeded",
            reason=reason or "publish/verification complete",
        )
    return finalize_session(
        state_root,
        session,
        run_id=run_id,
        status="failed",
        reason_code=reason_code or "publish_failed",
        reason=reason,
    )


def bind_session_to_job(job: Any, session: AgentSession) -> Any:
    """Return job copy with CT103 session_id (never alias to run_id)."""
    if hasattr(job, "model_copy"):
        return job.model_copy(update={"session_id": session.session_id})
    if isinstance(job, dict):
        out = dict(job)
        out["session_id"] = session.session_id
        return out
    raise TypeError(f"unsupported job type: {type(job)}")
