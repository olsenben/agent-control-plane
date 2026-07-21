"""Wire V6 T07 NL invocation lifecycle into state reduction (QA F-06)."""

from __future__ import annotations

import logging
from typing import Any

from agent_control.config import Settings
from agent_control.gitea_comments import post_issue_comment
from agent_control.invocation import (
    begin_invocation,
    mark_session_created,
    request_clarification,
    save_invocation,
)
from agent_control.nl_intent import extract_agent_intent, is_bare_at_agent
from agent_shared.models.invocation import InvocationRecord

logger = logging.getLogger(__name__)


def _comment_meta(trigger: dict[str, Any]) -> tuple[str, int | None, str | None, str]:
    payload = trigger.get("payload") or {}
    comment = payload.get("comment") or {}
    body = str(comment.get("body") or "")
    comment_id = comment.get("id")
    try:
        cid = int(comment_id) if comment_id is not None else None
    except (TypeError, ValueError):
        cid = None
    user = comment.get("user") or payload.get("sender") or {}
    login = str(user.get("login") or "unknown")
    delivery = trigger.get("delivery_id")
    return body, cid, str(delivery) if delivery else None, login


def maybe_begin_nl_invocation(
    state_root,
    project: str,
    trigger: dict[str, Any],
    *,
    settings: Settings,
) -> dict[str, Any]:
    """Start invocation FSM for bare ``@agent`` comments.

    clarify=True → caller must skip dispatch.
    """
    etype = str(trigger.get("type") or "")
    if etype not in ("gitea.issue_comment", "gitea.pr_comment"):
        return {"handled": False}
    body, comment_id, delivery_id, login = _comment_meta(trigger)
    if not is_bare_at_agent(body):
        return {"handled": False}

    intent = extract_agent_intent(body)
    issue = (trigger.get("payload") or {}).get("issue") or {}
    issue_number = issue.get("number")
    try:
        subject_number = int(issue_number) if issue_number is not None else None
    except (TypeError, ValueError):
        subject_number = None

    record = begin_invocation(
        state_root,
        project=project,
        raw_text=body,
        invoked_by=login,
        source_comment_id=comment_id,
        source_delivery_id=delivery_id,
        subject_number=subject_number,
        intent=intent,
    )

    if record.status in ("intent_ambiguous", "clarification_requested") or (
        intent.confidence < 0.7 or not intent.kind
    ):
        record = request_clarification(state_root, record)
        if subject_number is not None:
            q = intent.clarification_question or "Please clarify with `/agent <kind> …`."
            try:
                result = post_issue_comment(
                    project,
                    subject_number,
                    "\n".join(
                        [
                            "## Agent invocation — clarification needed",
                            "",
                            f"Invocation: `{record.invocation_id}`",
                            f"Invoker: `{login}`",
                            "",
                            q,
                        ]
                    ),
                    settings=settings,
                )
                if result and result.get("id"):
                    record = record.model_copy(
                        update={"invocation_comment_id": int(result["id"])}
                    )
                    save_invocation(state_root, record)
            except Exception:
                logger.exception("nl_clarification_comment_failed inv=%s", record.invocation_id)
        return {
            "handled": True,
            "clarify": True,
            "invocation_id": record.invocation_id,
            "invocation": record.model_dump(mode="json"),
        }

    return {
        "handled": True,
        "clarify": False,
        "invocation_id": record.invocation_id,
        "invocation": record.model_dump(mode="json"),
    }


def handoff_invocation_to_session(
    state_root,
    *,
    project: str,
    invocation_id: str | None,
    session_id: str,
    run_id: str,
    settings: Settings | None = None,
) -> InvocationRecord | None:
    """Mark session_created; post correlation stub with run_id (T07-F08)."""
    if not invocation_id:
        return None
    from agent_control.invocation import load_invocation

    record = load_invocation(state_root, project, invocation_id)
    if record is None:
        return None
    record = mark_session_created(
        state_root, record, session_id=session_id, run_id=run_id
    )
    if settings and record.subject_number is not None:
        stub = "\n".join(
            [
                "## Agent invocation — session created",
                "",
                f"Invocation: `{record.invocation_id}`",
                f"Run: `{run_id}`",
                f"Session: `{session_id}`",
                f"Observe: `/observe/sessions/{run_id}`",
                "",
                "Further status updates use the session comment.",
            ]
        )
        try:
            result = post_issue_comment(
                project, int(record.subject_number), stub, settings=settings
            )
            if result and result.get("id"):
                record = record.model_copy(
                    update={"invocation_comment_id": int(result["id"])}
                )
                save_invocation(state_root, record)
        except Exception:
            logger.exception("invocation_handoff_stub_failed inv=%s", record.invocation_id)
    return record
