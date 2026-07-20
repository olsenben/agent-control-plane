"""Gitea issue comments for approval workflow (CT103)."""

from __future__ import annotations

from agent_control.config import Settings, get_settings
from agent_control.gitea_client import GiteaClient
from agent_control.invocation_ack import (
    IdentityAudit,
    append_identity_footer,
    identity_audit_from_parts,
)
from agent_shared.models.approval import FixAuthorizedEvent, WorkItemApproval


def post_issue_comment(
    project: str,
    issue_number: int,
    body: str,
    settings: Settings | None = None,
) -> dict | None:
    settings = settings or get_settings()
    if not settings.gitea_bot_token:
        return None
    owner, repo = project.split("/", 1)
    client = GiteaClient(settings)
    import httpx

    url = f"{client.base_url}/api/v1/repos/{owner}/{repo}/issues/{issue_number}/comments"
    with httpx.Client(timeout=30.0) as http:
        resp = http.post(url, json={"body": body}, headers=client._headers())
        resp.raise_for_status()
        return resp.json()


def format_fix_blocked(
    *,
    target: str,
    reason: str | None,
    run_id: str | None = None,
    audit: IdentityAudit | None = None,
) -> str:
    lines = [
        "## Fix blocked (Risk 2)",
        "",
        f"Target: `{target}`",
        f"Reason: {reason or 'approval required'}",
    ]
    if run_id:
        lines.append(f"Run: `{run_id}`")
    lines.extend(
        [
            "",
            "Required steps:",
            f"1. `/agent approve {target}` (owner only)",
            f"2. `/agent fix {target}` after approval",
            "",
            "Slice 6B: enqueue CT104 fix worker after approval.",
        ]
    )
    body = "\n".join(lines)
    if audit is not None:
        return append_identity_footer(body, audit)
    return body


def format_fix_started(
    *,
    run_id: str,
    approval_target_id: str,
    allowed_files: list[str],
    remote_publish_enabled: bool = False,
    invoked_by: str | None = None,
    session_id: str | None = None,
    queue: str | None = "rlm-root",
    host: str | None = "ct104",
    audit: IdentityAudit | None = None,
    settings: Settings | None = None,
) -> str:
    files_line = ", ".join(f"`{f}`" for f in allowed_files[:8])
    if len(allowed_files) > 8:
        files_line += f" (+{len(allowed_files) - 8} more)"
    tail = (
        "CT104 will produce an immutable patch bundle; CT103 publish-broker "
        f"validates and may push `agent/{run_id}` + open PR (V4.1.1 / 6D.2)."
        if remote_publish_enabled
        else "CT104 is generating a workspace-local patch bundle (no remote publish)."
    )
    lines = [
        "## Fix started (Risk 2)",
        "",
        f"Run: `{run_id}`",
        "Command: `/agent fix`",
        f"Target: `{approval_target_id}`",
        f"Allowed files: {files_line or '(none)'}",
    ]
    if invoked_by:
        lines.append(f"Invoker: `{invoked_by}`")
    if queue:
        lines.append(f"Queue: `{queue}`")
    if host:
        lines.append(f"Host: `{host}`")
    lines.extend(["", tail])
    body = "\n".join(lines)
    footer = audit or identity_audit_from_parts(
        invoked_by=invoked_by or "unknown",
        run_id=run_id,
        session_id=session_id,
        settings=settings,
    )
    return append_identity_footer(body, footer)


def format_fix_enqueue_failed(
    *,
    target: str,
    reason: str,
    run_id: str | None = None,
    audit: IdentityAudit | None = None,
) -> str:
    lines = [
        "## Fix enqueue failed",
        "",
        f"Target: `{target}`",
        f"Reason: {reason}",
    ]
    if run_id:
        lines.append(f"Run: `{run_id}`")
    lines.extend(
        [
            "",
            "Approval was not consumed. Retry `/agent fix` after infra recovery.",
        ]
    )
    body = "\n".join(lines)
    if audit is not None:
        return append_identity_footer(body, audit)
    return body


def format_non_owner_approval() -> str:
    return "## Approval rejected\n\nOwner approval required for `/agent approve` and `/agent reject`."


def format_approval_granted(approval: WorkItemApproval) -> str:
    files_line = (
        ", ".join(approval.allowed_files)
        if approval.allowed_files
        else "(none — patch generation blocked until replan)"
    )
    return "\n".join(
        [
            "## Approval granted (Risk 2)",
            "",
            f"Approval ID: `{approval.approval_id}`",
            f"Target: `{approval.approval_target_id}`",
            f"Plan alias: `{approval.plan_alias}`",
            f"Plan hash: `{approval.plan_hash[:16]}...`",
            f"Blast radius hash: `{approval.blast_radius_hash[:16]}...`",
            f"Expires: {approval.expires_at}",
            f"Allowed files: {files_line}",
            "",
            f"To start fix: `/agent fix {approval.approval_target_id}`",
        ]
    )


def format_fix_authorized(body: FixAuthorizedEvent) -> str:
    enqueued = "true" if body.worker_enqueued else "false"
    return "\n".join(
        [
            "## Fix authorized",
            "",
            f"Approval ID: `{body.approval_id}`",
            f"Target: `{body.approval_target_id}`",
            f"Worker enqueued: **{enqueued}**",
            f"Dispatch target: {body.dispatch_target}",
            f"Fix run: `{body.fix_run_id or 'pending'}`",
        ]
    )


def format_approval_rejected(*, target: str, reason: str | None) -> str:
    msg = reason or "(no reason given)"
    return f"## Approval rejected\n\nTarget: `{target}`\nReason: {msg}"


def format_plan_resolution_error(message: str) -> str:
    return f"## Approval command failed\n\n{message}"
