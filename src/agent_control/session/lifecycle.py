"""Session lifecycle: create at dispatch, finalize by terminal owner."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_control.session.events import (
    append_session_blocked,
    append_session_failed,
    append_session_finished,
    append_session_started,
    append_subject_context_resolved,
    append_worker_mapped_event,
)
from agent_control.session.publish_candidate import is_publish_candidate
from agent_control.session.reasons import (
    SessionTerminalReason,
    SessionTerminalStatus,
    classify_unsuccessful_terminal,
    normalize_terminal,
)
from agent_control.session.storage import (
    SessionStoreError,
    load_blocked_request_index,
    load_session_by_run,
    lookup_session_id_by_run,
    persist_session_with_run_index,
    save_blocked_request_index,
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

# Commands that stay nonterminal through worker ingest; CI verification owns finish.
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
    subject_kind: SubjectKind | None = None,
    subject_number: int | None = None,
) -> tuple[SubjectKind, int]:
    if subject_kind is not None and subject_number is not None:
        return subject_kind, int(subject_number)
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


def _invoked_by_from_trigger(trigger_context: Any, *, fallback: str | None = None) -> str:
    if isinstance(trigger_context, dict):
        author = trigger_context.get("author")
    else:
        author = getattr(trigger_context, "author", None)
    return str(author or fallback or "unknown")


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
    subject_kind: SubjectKind | None = None,
    subject_number: int | None = None,
    invoked_by: str | None = None,
) -> AgentSession:
    """Build a new agent_session.v1 (not yet persisted)."""
    if command_kind not in TYPED_SESSION_COMMANDS:
        raise ValueError(f"typed sessions not used for command_kind={command_kind}")
    if not run_id.startswith("run-"):
        raise ValueError(f"run_id must use run- prefix: {run_id!r}")

    sid = session_id or make_session_id()
    if sid == run_id or sid.startswith("run-"):
        raise ValueError("session_id must be distinct from run_id")

    kind, number = _subject_from_trigger(
        trigger_context,
        command_kind=command_kind,
        subject_kind=subject_kind,
        subject_number=subject_number,
    )
    _, repo = split_project(project)
    repo_full = normalize_repo_full_name(project) or project
    input_sha = compute_input_state_sha(
        project=repo_full,
        subject_kind=kind,
        subject_number=number,
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
        subject_kind=kind,
        subject_number=number,
        command_kind=command_kind,
        status=SessionStatus.CREATED,
        run_ids=[run_id],
        correlation_id=make_correlation_id(session_id=sid, run_id=run_id),
        input_state_sha=input_sha,
        head_sha=head_sha or "",
        policy_source_sha=policy_source_sha or "",
        risk_level=risk_level_for_command(command_kind),
        risk_tags=tags,
        invoked_by=_invoked_by_from_trigger(trigger_context, fallback=invoked_by),
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
    subject_kind: SubjectKind | None = None,
    subject_number: int | None = None,
    invoked_by: str | None = None,
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
        subject_kind=subject_kind,
        subject_number=subject_number,
        invoked_by=invoked_by,
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
    status: SessionTerminalStatus,
    reason_code: SessionTerminalReason,
    reason: str | None = None,
    domain_reasons: list[str] | None = None,
) -> AgentSession:
    """Terminal transition + ledger event. Idempotent for same terminal+reason."""
    _, canonical, detail = normalize_terminal(
        status,
        reason_code,
        domain_reasons=domain_reasons,
        message=reason,
    )
    reason_value = canonical.value
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
            terminal_reason_code=reason_value,
            terminal_reason=detail,
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
        return session

    save_session(state_root, updated)
    if status == "finished":
        append_session_finished(state_root, updated, run_id=run_id)
    elif status == "failed":
        append_session_failed(
            state_root,
            updated,
            run_id=run_id,
            reason_code=reason_value,
            reason=detail,
        )
    else:
        append_session_blocked(
            state_root,
            updated,
            run_id=run_id,
            reason_code=reason_value,
            reason=detail,
        )
    return updated


def finalize_session_blocked(
    state_root: Path,
    session: AgentSession,
    *,
    run_id: str,
    reason_code: SessionTerminalReason,
    reason: str | None = None,
    domain_reasons: list[str] | None = None,
) -> AgentSession:
    return finalize_session(
        state_root,
        session,
        run_id=run_id,
        status="blocked",
        reason_code=reason_code,
        reason=reason,
        domain_reasons=domain_reasons,
    )


def make_blocked_request_key(
    *,
    project: str,
    command_kind: str,
    issue_id: int | None,
    comment_id: int | None,
    trigger_event_id: str | None,
    approval_target_id: str | None = None,
    plan_hash: str | None = None,
) -> str:
    parts = [
        project,
        command_kind,
        str(issue_id or ""),
        str(comment_id or trigger_event_id or ""),
        approval_target_id or "",
        plan_hash or "",
    ]
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()[:24]
    return f"blocked-{digest}"


def deterministic_blocked_run_id(request_key: str) -> str:
    digest = hashlib.sha256(request_key.encode()).hexdigest()[:28]
    return f"run-{digest}"


def begin_and_block_typed_session(
    state_root: Path,
    *,
    project: str,
    command_kind: CommandKind,
    request_key: str,
    head_sha: str,
    trigger_context: Any,
    reason_code: SessionTerminalReason,
    reason: str | None = None,
    domain_reasons: list[str] | None = None,
    policy_source_sha: str = "",
    subject_kind: SubjectKind | None = None,
    subject_number: int | None = None,
    invoked_by: str | None = None,
) -> AgentSession:
    """Idempotent compound helper: create blocked session or return existing."""
    existing_index = load_blocked_request_index(state_root, project, request_key)
    if existing_index:
        sid = existing_index.get("session_id")
        run_id = existing_index.get("run_id")
        if isinstance(sid, str) and isinstance(run_id, str):
            loaded = load_session_by_run(state_root, project, run_id)
            if loaded is not None:
                if loaded.status not in (
                    SessionStatus.BLOCKED,
                    SessionStatus.FINISHED,
                    SessionStatus.FAILED,
                ):
                    return finalize_session_blocked(
                        state_root,
                        loaded,
                        run_id=run_id,
                        reason_code=reason_code,
                        reason=reason,
                        domain_reasons=domain_reasons,
                    )
                return loaded

    run_id = deterministic_blocked_run_id(request_key)
    existing = load_session_by_run(state_root, project, run_id)
    if existing is not None:
        if existing.status != SessionStatus.BLOCKED:
            return finalize_session_blocked(
                state_root,
                existing,
                run_id=run_id,
                reason_code=reason_code,
                reason=reason,
                domain_reasons=domain_reasons,
            )
        save_blocked_request_index(
            state_root,
            project=project,
            request_key=request_key,
            session_id=existing.session_id,
            run_id=run_id,
        )
        return existing

    session = begin_typed_session(
        state_root,
        project=project,
        command_kind=command_kind,
        run_id=run_id,
        head_sha=head_sha,
        trigger_context=trigger_context,
        policy_source_sha=policy_source_sha,
        subject_kind=subject_kind,
        subject_number=subject_number,
        invoked_by=invoked_by,
    )
    try:
        blocked = finalize_session_blocked(
            state_root,
            session,
            run_id=run_id,
            reason_code=reason_code,
            reason=reason,
            domain_reasons=domain_reasons,
        )
    except Exception:
        # Replay path: session may exist without terminal if prior attempt failed mid-flight.
        replay = load_session_by_run(state_root, project, run_id)
        if replay is not None and replay.status == SessionStatus.BLOCKED:
            blocked = replay
        else:
            raise
    save_blocked_request_index(
        state_root,
        project=project,
        request_key=request_key,
        session_id=blocked.session_id,
        run_id=run_id,
    )
    return blocked


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
        reason_code=SessionTerminalReason.ENQUEUE_FAILED,
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
    *,
    remote_publish_enabled: bool = True,
) -> dict[str, Any]:
    """Apply ingest-time session rules. Returns action summary.

    - Mismatch → raise SessionMismatchError (caller must not finalize / map).
    - review/plan → terminal finished|failed|blocked.
    - fix/repair → running when publish candidate; else terminal failed|blocked.
    """
    try:
        session = resolve_session_for_ingest(state_root, event)
    except LookupError:
        return {"skipped": True, "reason": "no_typed_session"}

    map_worker_allowlisted_events(
        state_root, session, run_id=event.run_id, event=event
    )

    kind = session.command_kind

    if event.policy_decision == "deny":
        updated = finalize_session_blocked(
            state_root,
            session,
            run_id=event.run_id,
            reason_code=SessionTerminalReason.POLICY_DENIED,
            reason=event.summary[:500] if event.summary else "policy denied",
            domain_reasons=list(event.diff_gate_violation_codes or []),
        )
        return {
            "skipped": False,
            "session_id": updated.session_id,
            "status": updated.status.value,
            "terminal": True,
        }

    if kind in PUBLISH_TERMINAL_OWNERS:
        if is_publish_candidate(event, remote_publish_enabled=remote_publish_enabled):
            updated = mark_session_running(state_root, session)
            return {
                "skipped": False,
                "session_id": updated.session_id,
                "status": updated.status.value,
                "terminal": False,
            }
        terminal_status, reason = classify_unsuccessful_terminal(
            domain_reasons=[event.terminal_status or "", event.fix_status or ""],
            policy_decision=event.policy_decision,
        )
        updated = finalize_session(
            state_root,
            session,
            run_id=event.run_id,
            status=terminal_status,
            reason_code=reason,
            reason=event.summary[:500] if event.summary else "worker failed",
            domain_reasons=[c for c in [event.terminal_status, event.fix_status] if c],
        )
        return {
            "skipped": False,
            "session_id": updated.session_id,
            "status": updated.status.value,
            "terminal": True,
        }

    if kind in INGEST_TERMINAL_OWNERS:
        success = event.status == "completed" and event.terminal_status in (
            None,
            "completed",
        )
        if success:
            from agent_control.session.verification import emit_ingest_verification_missing

            session = emit_ingest_verification_missing(
                state_root, session, run_id=event.run_id
            )
            updated = finalize_session(
                state_root,
                session,
                run_id=event.run_id,
                status="finished",
                reason_code=SessionTerminalReason.INGEST_COMPLETED,
                reason="validated result persisted",
            )
            _maybe_admit_session_memory(state_root, updated, event)
        else:
            terminal_status, reason = classify_unsuccessful_terminal(
                domain_reasons=[event.terminal_status or ""],
                policy_decision=event.policy_decision,
            )
            updated = finalize_session(
                state_root,
                session,
                run_id=event.run_id,
                status=terminal_status,
                reason_code=reason,
                reason=event.summary[:500] if event.summary else "worker failed",
                domain_reasons=[event.terminal_status] if event.terminal_status else None,
            )
        return {
            "skipped": False,
            "session_id": updated.session_id,
            "status": updated.status.value,
            "terminal": True,
        }

    return {"skipped": True, "reason": f"unhandled_command_kind:{kind}"}


def _maybe_admit_session_memory(
    state_root: Path,
    session: AgentSession,
    event: AgentRunCompletedEvent,
) -> None:
    """Slice 5.7: selective writeback after session_finished (review/plan)."""
    from agent_control.memory.session_writeback import admit_session_trace_memory
    from agent_control.session.events import append_memory_admitted, append_memory_rejected

    result = admit_session_trace_memory(state_root, session, event)
    if result.get("admitted"):
        append_memory_admitted(
            state_root,
            session,
            run_id=event.run_id,
            record_id=str(result["record_id"]),
            epistemic_status=str(result["epistemic_status"]),
            evidence_refs=list(result.get("evidence_refs") or []),
        )
    else:
        append_memory_rejected(
            state_root,
            session,
            run_id=event.run_id,
            reason=str(result.get("reason") or "rejected"),
        )


def handle_publish_session_terminal(
    state_root: Path,
    *,
    project: str,
    run_id: str,
    terminal: SessionTerminalStatus,
    reason_code: SessionTerminalReason,
    reason: str | None = None,
    domain_reasons: list[str] | None = None,
) -> AgentSession | None:
    """Fix/repair terminal owner — publish reject / CI verification path."""
    session = load_session_by_run(state_root, project, run_id)
    if session is None:
        return None
    if session.command_kind not in PUBLISH_TERMINAL_OWNERS:
        return session
    return finalize_session(
        state_root,
        session,
        run_id=run_id,
        status=terminal,
        reason_code=reason_code,
        reason=reason,
        domain_reasons=domain_reasons,
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
