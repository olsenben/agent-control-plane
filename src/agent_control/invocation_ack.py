"""Invocation acknowledgement + acting vs invoker identity (T10).

Every accepted ``/agent …`` command should produce a visible started ack and a
terminal success/failure/blocked comment correlated by ``run_id``. Bot posts use
``acting_identity`` (``agent-bot`` / ``GITEA_BOT_TOKEN``); humans are recorded as
``invoked_by`` only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from agent_control.config import Settings, get_settings
from agent_shared.constants import QUEUE_RLM_ROOT

DEFAULT_ACTING_IDENTITY = "agent-bot"
DEFAULT_WORKER_HOST = "ct104"

TerminalOutcome = Literal["success", "failure", "blocked"]


@dataclass(frozen=True)
class IdentityAudit:
    """Audit fields for session events + comment footers."""

    acting_identity: str
    invoked_by: str
    invoked_by_id: int | None = None
    approved_by: str | None = None
    source_comment_id: int | None = None
    source_delivery_id: str | None = None
    run_id: str | None = None
    session_id: str | None = None

    def footer_lines(self) -> list[str]:
        lines = [
            "---",
            f"acting_identity: `{self.acting_identity}`",
            f"invoked_by: `{self.invoked_by}`",
        ]
        if self.approved_by:
            lines.append(f"approved_by: `{self.approved_by}`")
        if self.invoked_by_id is not None:
            lines.append(f"invoked_by_id: `{self.invoked_by_id}`")
        if self.source_comment_id is not None:
            lines.append(f"source_comment_id: `{self.source_comment_id}`")
        if self.source_delivery_id:
            lines.append(f"source_delivery_id: `{self.source_delivery_id}`")
        if self.run_id:
            lines.append(f"run_id: `{self.run_id}`")
        if self.session_id:
            lines.append(f"session_id: `{self.session_id}`")
        return lines


def resolve_acting_identity(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    value = (settings.gitea_acting_identity or "").strip()
    return value or DEFAULT_ACTING_IDENTITY


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def invoker_fields_from_trigger(
    trigger_context: Any,
    *,
    delivery_id: str | None = None,
    fallback_login: str | None = None,
) -> dict[str, Any]:
    """Extract human invoker + source ids from TriggerContext or dict."""
    if isinstance(trigger_context, dict):
        author = trigger_context.get("author")
        author_id = trigger_context.get("author_id")
        comment_id = trigger_context.get("comment_id")
    else:
        author = getattr(trigger_context, "author", None)
        author_id = getattr(trigger_context, "author_id", None)
        comment_id = getattr(trigger_context, "comment_id", None)
    return {
        "invoked_by": str(author or fallback_login or "unknown"),
        "invoked_by_id": _as_int(author_id),
        "source_comment_id": _as_int(comment_id),
        "source_delivery_id": (delivery_id or None) or None,
    }


def identity_audit_from_session(
    session: Any,
    *,
    run_id: str | None = None,
    settings: Settings | None = None,
) -> IdentityAudit:
    acting = getattr(session, "acting_identity", None) or resolve_acting_identity(settings)
    rid = run_id
    if not rid:
        run_ids = getattr(session, "run_ids", None) or []
        rid = run_ids[0] if run_ids else None
    return IdentityAudit(
        acting_identity=str(acting),
        invoked_by=str(getattr(session, "invoked_by", None) or "unknown"),
        invoked_by_id=getattr(session, "invoked_by_id", None),
        approved_by=getattr(session, "approved_by", None),
        source_comment_id=getattr(session, "source_comment_id", None),
        source_delivery_id=getattr(session, "source_delivery_id", None),
        run_id=rid,
        session_id=getattr(session, "session_id", None),
    )


def identity_audit_from_parts(
    *,
    invoked_by: str,
    run_id: str | None = None,
    session_id: str | None = None,
    invoked_by_id: int | None = None,
    approved_by: str | None = None,
    source_comment_id: int | None = None,
    source_delivery_id: str | None = None,
    settings: Settings | None = None,
) -> IdentityAudit:
    return IdentityAudit(
        acting_identity=resolve_acting_identity(settings),
        invoked_by=invoked_by or "unknown",
        invoked_by_id=invoked_by_id,
        approved_by=approved_by,
        source_comment_id=source_comment_id,
        source_delivery_id=source_delivery_id,
        run_id=run_id,
        session_id=session_id,
    )


def format_identity_footer(audit: IdentityAudit) -> str:
    return "\n".join(audit.footer_lines())


def append_identity_footer(body: str, audit: IdentityAudit) -> str:
    """Append identity footer once (idempotent if footer already present)."""
    text = (body or "").rstrip()
    marker = f"acting_identity: `{audit.acting_identity}`"
    if marker in text and f"invoked_by: `{audit.invoked_by}`" in text:
        return text
    if not text:
        return format_identity_footer(audit)
    return f"{text}\n\n{format_identity_footer(audit)}"


def format_invocation_started(
    *,
    command: str,
    run_id: str,
    invoked_by: str,
    session_id: str | None = None,
    queue: str | None = QUEUE_RLM_ROOT,
    host: str | None = DEFAULT_WORKER_HOST,
    extra_lines: list[str] | None = None,
    invoked_by_id: int | None = None,
    source_comment_id: int | None = None,
    source_delivery_id: str | None = None,
    settings: Settings | None = None,
) -> str:
    """Visible started ack posted on accept (webhook → enqueue succeeded)."""
    title = command.strip().lower() or "command"
    lines = [
        f"## Agent started (`{title}`)",
        "",
        f"Run: `{run_id}`",
        f"Command: `/agent {title}`",
        f"Invoker: `{invoked_by}`",
    ]
    if queue:
        lines.append(f"Queue: `{queue}`")
    if host:
        lines.append(f"Host: `{host}`")
    if extra_lines:
        lines.append("")
        lines.extend(extra_lines)
    audit = identity_audit_from_parts(
        invoked_by=invoked_by,
        run_id=run_id,
        session_id=session_id,
        invoked_by_id=invoked_by_id,
        source_comment_id=source_comment_id,
        source_delivery_id=source_delivery_id,
        settings=settings,
    )
    return append_identity_footer("\n".join(lines), audit)


def format_invocation_terminal(
    *,
    outcome: TerminalOutcome,
    command: str,
    run_id: str,
    invoked_by: str,
    reason: str | None = None,
    reason_code: str | None = None,
    session_id: str | None = None,
    detail_lines: list[str] | None = None,
    invoked_by_id: int | None = None,
    source_comment_id: int | None = None,
    source_delivery_id: str | None = None,
    settings: Settings | None = None,
) -> str:
    """Terminal success / failure / blocked comment (same run_id as started ack)."""
    title = command.strip().lower() or "command"
    heading = {
        "success": f"## Agent finished (`{title}`)",
        "failure": f"## Agent failed (`{title}`)",
        "blocked": f"## Agent blocked (`{title}`)",
    }[outcome]
    lines = [
        heading,
        "",
        f"Run: `{run_id}`",
        f"Outcome: **{outcome}**",
    ]
    if reason_code:
        lines.append(f"Reason code: `{reason_code}`")
    if reason:
        lines.append(f"Reason: {reason}")
    if detail_lines:
        lines.append("")
        lines.extend(detail_lines)
    audit = identity_audit_from_parts(
        invoked_by=invoked_by,
        run_id=run_id,
        session_id=session_id,
        invoked_by_id=invoked_by_id,
        source_comment_id=source_comment_id,
        source_delivery_id=source_delivery_id,
        settings=settings,
    )
    return append_identity_footer("\n".join(lines), audit)
