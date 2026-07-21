"""Versioned Gitea session status comment projection (V6 T02)."""

from __future__ import annotations

import logging
from typing import Any, Literal

from agent_control.config import Settings, get_settings
from agent_control.gitea_comments import post_issue_comment
from agent_control.invocation_ack import (
    IdentityAudit,
    append_identity_footer,
    identity_audit_from_session,
)
from agent_control.session.storage import save_session
from agent_shared.models.agent_session import AgentSession

logger = logging.getLogger(__name__)

SessionDisplayStatus = Literal[
    "queued",
    "running",
    "waiting_for_ci",
    "completed",
    "failed",
    "blocked",
    "cancelled",
    "verification_failed",
    "verification_missing",
    "needs_human",
]

# Monotonic rank — terminal states share high rank; non-terminal increases.
_STATUS_RANK: dict[str, int] = {
    "queued": 10,
    "running": 20,
    "waiting_for_ci": 30,
    "needs_human": 35,
    "verification_missing": 36,
    "verification_failed": 90,
    "completed": 100,
    "failed": 100,
    "blocked": 100,
    "cancelled": 100,
}


def display_status_from_session(session: AgentSession) -> SessionDisplayStatus:
    code = (session.terminal_reason_code or "").lower()
    if session.status.value == "finished":
        if "verification" in code and "missing" in code:
            return "verification_missing"
        if "verification" in code and "fail" in code:
            return "verification_failed"
        return "completed"
    if session.status.value == "failed":
        if "verification" in code:
            return "verification_failed"
        return "failed"
    if session.status.value == "blocked":
        if "human" in code or "approval" in code:
            return "needs_human"
        return "blocked"
    if session.status.value == "running":
        if "ci" in code or "verification" in code:
            return "waiting_for_ci"
        return "running"
    return "queued"


def _status_heading(status: SessionDisplayStatus, command: str) -> str:
    labels = {
        "queued": "Queued",
        "running": "Running",
        "waiting_for_ci": "Waiting for CI",
        "completed": "Completed",
        "failed": "Failed",
        "blocked": "Blocked",
        "cancelled": "Cancelled",
        "verification_failed": "Verification failed",
        "verification_missing": "Verification missing",
        "needs_human": "Needs human",
    }
    return f"## Agent session — {labels.get(status, status)} (`{command}`)"


def render_session_comment_body(
    *,
    session: AgentSession,
    run_id: str,
    display_status: SessionDisplayStatus,
    command: str,
    detail_lines: list[str] | None = None,
    settings: Settings | None = None,
) -> str:
    lines = [
        _status_heading(display_status, command),
        "",
        f"Run: `{run_id}`",
        f"Command: `/agent {command}`",
        f"Status: **{display_status}**",
        f"Invoker: `{session.invoked_by}`",
    ]
    if session.terminal_reason:
        lines.append(f"Reason: {session.terminal_reason}")
    if detail_lines:
        lines.extend(["", *detail_lines])
    audit = identity_audit_from_session(session, run_id=run_id, settings=settings)
    return append_identity_footer("\n".join(lines), audit)


def _should_apply_update(session: AgentSession, *, event_sequence: int, display_status: str) -> bool:
    if event_sequence <= (session.last_rendered_event_sequence or 0):
        return False
    prev = session.last_rendered_status or ""
    if prev and _STATUS_RANK.get(display_status, 0) < _STATUS_RANK.get(prev, 0):
        return False
    return True


def patch_issue_comment(
    project: str,
    comment_id: int,
    body: str,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    settings = settings or get_settings()
    if not settings.gitea_bot_token:
        return None
    from agent_control.gitea_client import GiteaClient

    owner, repo = project.split("/", 1)
    client = GiteaClient(settings)
    return client.patch_issue_comment(owner, repo, comment_id, body)


def project_session_comment(
    state_root: Any,
    session: AgentSession,
    *,
    run_id: str,
    command: str,
    display_status: SessionDisplayStatus | None = None,
    event_sequence: int | None = None,
    issue_number: int | None = None,
    detail_lines: list[str] | None = None,
    settings: Settings | None = None,
) -> AgentSession:
    """Single-writer comment projection with version + sequence guards."""
    settings = settings or get_settings()
    status = display_status or display_status_from_session(session)
    seq = event_sequence if event_sequence is not None else (session.last_rendered_event_sequence or 0) + 1

    if session.session_comment_id and not _should_apply_update(session, event_sequence=seq, display_status=status):
        return session

    body = render_session_comment_body(
        session=session,
        run_id=run_id,
        display_status=status,
        command=command,
        detail_lines=detail_lines,
        settings=settings,
    )
    issue = issue_number if issue_number is not None else session.subject_number
    if issue is None:
        return session

    comment_id = session.session_comment_id
    result: dict[str, Any] | None = None
    try:
        if comment_id:
            result = patch_issue_comment(session.project, int(comment_id), body, settings=settings)
        else:
            result = post_issue_comment(session.project, int(issue), body, settings=settings)
    except Exception:
        logger.exception(
            "session_comment_projection_failed session=%s run=%s status=%s",
            session.session_id,
            run_id,
            status,
        )
        return session

    if not result:
        return session

    new_id = int(result.get("id") or comment_id or 0)
    updated = session.model_copy(
        update={
            "session_comment_id": new_id or session.session_comment_id,
            "session_comment_version": (session.session_comment_version or 0) + 1,
            "last_rendered_event_sequence": seq,
            "last_rendered_status": status,
        }
    )
    save_session(state_root, updated)
    return updated


def post_invocation_rejected_comment(
    project: str,
    issue_number: int,
    *,
    reason: str,
    audit: IdentityAudit | None = None,
    settings: Settings | None = None,
) -> None:
    lines = [
        "## Agent invocation rejected",
        "",
        f"Reason: {reason}",
    ]
    body = "\n".join(lines)
    if audit is not None:
        body = append_identity_footer(body, audit)
    try:
        post_issue_comment(project, issue_number, body, settings=settings)
    except Exception:
        logger.exception("invocation_rejected_comment_failed project=%s issue=%s", project, issue_number)


def post_session_comment_successor(
    session: AgentSession,
    *,
    run_id: str,
    command: str,
    display_status: SessionDisplayStatus,
    reason: str,
    settings: Settings | None = None,
) -> AgentSession:
    """Post successor comment when PATCH permanently fails; persist new comment id."""
    settings = settings or get_settings()
    if session.subject_number is None:
        return session
    detail = [f"Note: successor comment (prior id `{session.session_comment_id}` unavailable)", reason]
    body = render_session_comment_body(
        session=session,
        run_id=run_id,
        display_status=display_status,
        command=command,
        detail_lines=detail,
        settings=settings,
    )
    try:
        result = post_issue_comment(session.project, session.subject_number, body, settings=settings)
    except Exception:
        logger.exception("successor_comment_failed session=%s", session.session_id)
        return session
    if not result:
        return session
    return session.model_copy(
        update={
            "session_comment_id": int(result["id"]),
            "session_comment_version": (session.session_comment_version or 0) + 1,
            "last_rendered_status": display_status,
        }
    )
