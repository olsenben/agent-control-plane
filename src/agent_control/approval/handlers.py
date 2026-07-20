"""State worker handlers for approve / reject / fix (Slice 6A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_control.approval.dispatch_fix import enqueue_fix_after_authorization, fix_remote_publish_enabled
from agent_control.approval.service import (
    authorize_fix,
    evaluate_fix_request,
    grant_approval,
    record_fix_request,
    reject_approval,
)
from agent_control.config import Settings, get_settings
from agent_control.gitea_comments import (
    format_approval_granted,
    format_approval_rejected,
    format_fix_blocked,
    format_fix_enqueue_failed,
    format_fix_started,
    format_non_owner_approval,
    format_plan_resolution_error,
    post_issue_comment,
)
from agent_control.project_registry import build_trigger_context
from agent_control.session import (
    begin_and_block_typed_session,
    make_blocked_request_key,
    map_fix_evaluation_to_block_reason,
)
from agent_shared.models.intent import CommandIntent


def _issue_number(trigger_event: dict[str, Any]) -> int | None:
    payload = trigger_event.get("payload") or {}
    issue = payload.get("issue") or {}
    number = issue.get("number")
    return int(number) if number is not None else None


def _comment_id(trigger_event: dict[str, Any]) -> int | None:
    payload = trigger_event.get("payload") or {}
    comment = payload.get("comment") or {}
    cid = comment.get("id")
    return int(cid) if cid is not None else None


def _block_fix_session(
    state_root: Path,
    *,
    project: str,
    issue_id: int,
    trigger_event: dict[str, Any],
    tc: dict[str, Any],
    target: str,
    evaluation_reason: str | None,
    comment_id: int | None,
    empty_allowed_files: bool = False,
    plan_hash: str | None = None,
    approval_target_id: str | None = None,
    head_sha: str = "",
) -> dict[str, str]:
    reason_code = map_fix_evaluation_to_block_reason(
        evaluation_reason=evaluation_reason,
        empty_allowed_files=empty_allowed_files,
    )
    request_key = make_blocked_request_key(
        project=project,
        command_kind="fix",
        issue_id=issue_id,
        comment_id=comment_id,
        trigger_event_id=str(trigger_event.get("event_id") or ""),
        approval_target_id=approval_target_id,
        plan_hash=plan_hash,
    )
    session = begin_and_block_typed_session(
        state_root,
        project=project,
        command_kind="fix",
        request_key=request_key,
        head_sha=head_sha,
        trigger_context=tc,
        reason_code=reason_code,
        reason=evaluation_reason,
        subject_kind="issue",
        subject_number=issue_id,
        invoked_by=str(tc.get("author") or "unknown"),
    )
    run_id = session.run_ids[0] if session.run_ids else ""
    return {
        "session_id": session.session_id,
        "run_id": run_id,
        "terminal_reason_code": reason_code.value,
    }


def handle_approval_commands(
    state_root: Path,
    project: str,
    trigger_event: dict[str, Any],
    intent: CommandIntent,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    issue_id = _issue_number(trigger_event)
    if issue_id is None or not intent.approval_target:
        return {"handled": False, "reason": "missing_issue_or_target"}

    body = (trigger_event.get("payload") or {}).get("comment", {}).get("body", "")
    tc = build_trigger_context(trigger_event, body, settings=settings)
    author_is_owner = bool(tc.get("author_is_owner"))
    author = tc.get("author") or "unknown"
    comment_id = _comment_id(trigger_event)
    target = intent.approval_target

    if intent.kind == "approve":
        approval, message, created = grant_approval(
            state_root,
            project=project,
            issue_id=issue_id,
            target=target,
            approver_login=author,
            author_is_owner=author_is_owner,
            comment_id=comment_id,
            source_url=tc.get("comment_url"),
            command_text=body,
        )
        if not author_is_owner:
            post_issue_comment(project, issue_id, format_non_owner_approval(), settings=settings)
        elif approval and created:
            post_issue_comment(project, issue_id, format_approval_granted(approval), settings=settings)
        elif not approval:
            post_issue_comment(project, issue_id, format_plan_resolution_error(message), settings=settings)
        return {
            "handled": True,
            "kind": "approve",
            "created": created,
            "approval_id": approval.approval_id if approval else None,
            "message": message,
        }

    if intent.kind == "reject":
        ok, message, created = reject_approval(
            state_root,
            project=project,
            issue_id=issue_id,
            target=target,
            rejector_login=author,
            author_is_owner=author_is_owner,
            reject_reason=intent.reject_reason,
            comment_id=comment_id,
        )
        if not author_is_owner:
            post_issue_comment(project, issue_id, format_non_owner_approval(), settings=settings)
        elif ok and created:
            post_issue_comment(
                project,
                issue_id,
                format_approval_rejected(target=target, reason=intent.reject_reason),
                settings=settings,
            )
        elif not ok:
            post_issue_comment(project, issue_id, format_plan_resolution_error(message), settings=settings)
        return {"handled": True, "kind": "reject", "created": created, "ok": ok, "message": message}

    if intent.kind == "fix":
        evaluation = evaluate_fix_request(
            state_root,
            project=project,
            issue_id=issue_id,
            target=target,
        )
        _, fix_req_created = record_fix_request(
            state_root,
            project=project,
            issue_id=issue_id,
            target=target,
            requested_by_login=author,
            comment_id=comment_id,
            evaluation=evaluation,
        )
        result: dict[str, Any] = {
            "handled": True,
            "kind": "fix",
            "fix_requested_created": fix_req_created,
            "policy_decision": evaluation.policy_decision,
        }
        if evaluation.policy_decision == "blocked":
            if fix_req_created:
                post_issue_comment(
                    project,
                    issue_id,
                    format_fix_blocked(target=target, reason=evaluation.reason),
                    settings=settings,
                )
            plan_hash = evaluation.plan_record.plan_hash if evaluation.plan_record else None
            approval_target_id = (
                evaluation.plan_record.approval_target_id if evaluation.plan_record else None
            )
            head_sha = ""
            if evaluation.approval:
                head_sha = evaluation.approval.approved_base_sha or ""
            block_info = _block_fix_session(
                state_root,
                project=project,
                issue_id=issue_id,
                trigger_event=trigger_event,
                tc=tc,
                target=target,
                evaluation_reason=evaluation.reason,
                comment_id=comment_id,
                plan_hash=plan_hash,
                approval_target_id=approval_target_id,
                head_sha=head_sha,
            )
            result.update(block_info)
            result["reason"] = evaluation.reason
            return result

        authorized, _, auth_created = authorize_fix(
            state_root,
            evaluation=evaluation,
            comment_id=comment_id,
        )
        result["fix_authorized_created"] = auth_created
        if evaluation.approval is None or evaluation.plan_record is None:
            return result

        if not evaluation.approval.allowed_files:
            if auth_created:
                post_issue_comment(
                    project,
                    issue_id,
                    format_fix_blocked(
                        target=target,
                        reason="Plan lacks explicit file scope (allowed_files empty)",
                    ),
                    settings=settings,
                )
            block_info = _block_fix_session(
                state_root,
                project=project,
                issue_id=issue_id,
                trigger_event=trigger_event,
                tc=tc,
                target=target,
                evaluation_reason="empty_allowed_files",
                comment_id=comment_id,
                empty_allowed_files=True,
                plan_hash=evaluation.plan_record.plan_hash,
                approval_target_id=evaluation.approval.approval_target_id,
                head_sha=evaluation.approval.approved_base_sha or "",
            )
            result.update(block_info)
            result["reason"] = "empty_allowed_files"
            return result

        if not auth_created:
            return result

        enqueue_result = enqueue_fix_after_authorization(
            state_root,
            trigger_event=trigger_event,
            approval=evaluation.approval,
            plan_record=evaluation.plan_record,
            comment_id=comment_id,
            settings=settings,
        )
        result["enqueue"] = enqueue_result
        if enqueue_result.get("enqueued"):
            post_issue_comment(
                project,
                issue_id,
                format_fix_started(
                    run_id=str(enqueue_result["run_id"]),
                    approval_target_id=evaluation.approval.approval_target_id,
                    allowed_files=evaluation.approval.allowed_files,
                    remote_publish_enabled=fix_remote_publish_enabled(settings),
                ),
                settings=settings,
            )
        else:
            reason = str(enqueue_result.get("reason", "enqueue failed"))
            if reason != "deduplicated":
                post_issue_comment(
                    project,
                    issue_id,
                    format_fix_enqueue_failed(
                        target=target,
                        reason=reason,
                    ),
                    settings=settings,
                )
        return result

    return {"handled": False, "reason": "unsupported_kind"}
