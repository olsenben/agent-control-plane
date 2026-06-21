"""Gitea issue comments for approval workflow (CT103)."""

from __future__ import annotations

from agent_control.config import Settings, get_settings
from agent_control.gitea_client import GiteaClient
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
) -> str:
    lines = [
        "## Fix blocked (Risk 2)",
        "",
        f"Target: `{target}`",
        f"Reason: {reason or 'approval required'}",
        "",
        "Required steps:",
        f"1. `/agent approve {target}` (owner only)",
        f"2. `/agent fix {target}` after approval",
        "",
        "Slice 6A: no worker enqueued; CT104 writes deferred to 6B.",
    ]
    return "\n".join(lines)


def format_non_owner_approval() -> str:
    return "## Approval rejected\n\nOwner approval required for `/agent approve` and `/agent reject`."


def format_approval_granted(approval: WorkItemApproval) -> str:
    files_line = ", ".join(approval.allowed_files) if approval.allowed_files else "(none — patch generation blocked until replan)"
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
            f"To authorize fix (dry-run): `/agent fix {approval.approval_target_id}`",
        ]
    )


def format_fix_authorized(body: FixAuthorizedEvent) -> str:
    return "\n".join(
        [
            "## Fix authorized (dry-run)",
            "",
            f"Approval ID: `{body.approval_id}`",
            f"Target: `{body.approval_target_id}`",
            "Worker enqueued: **false**",
            "Dispatch target: none",
            "Next slice: **6B** (local patch generation)",
            "",
            "No CT104 writes in Slice 6A.",
        ]
    )


def format_approval_rejected(*, target: str, reason: str | None) -> str:
    msg = reason or "(no reason given)"
    return f"## Approval rejected\n\nTarget: `{target}`\nReason: {msg}"


def format_plan_resolution_error(message: str) -> str:
    return f"## Approval command failed\n\n{message}"
