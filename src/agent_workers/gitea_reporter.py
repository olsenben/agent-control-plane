"""Optional Gitea comment posting from worker-report."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from agent_shared.models.events import AgentRunCompletedEvent
from agent_workers.security.redactor import SecretRedactor
from agent_workers.settings import WorkerSettings


def maybe_post_comment(
    settings: WorkerSettings,
    job: dict[str, Any],
    completed: AgentRunCompletedEvent,
    artifact_root: Path,
) -> dict[str, Any]:
    if not settings.gitea_agent_comment_enabled or not settings.gitea_agent_token:
        return {"status": "skipped", "reason": "comments_disabled_or_no_token"}

    trigger = job.get("trigger_context") or {}
    issue_number = trigger.get("issue_number")
    if not issue_number:
        return {"status": "skipped", "reason": "no_issue_number"}

    owner, repo = completed.project.split("/", 1)
    url = f"{settings.gitea_base_url.rstrip('/')}/api/v1/repos/{owner}/{repo}/issues/{issue_number}/comments"
    mention = trigger.get("author", "")
    if completed.agent == "reviewer" or completed.flow == "code_review":
        body = (
            f"@{mention} Agent run `{completed.run_id}` **{completed.status}** "
            f"({completed.flow}/{completed.agent}, risk={completed.risk_class}).\n\n"
            f"{completed.summary}"
        )
    else:
        body = (
            f"@{mention} Agent run `{completed.run_id}` **{completed.status}** "
            f"({completed.flow}/{completed.agent}, risk={completed.risk_class}).\n\n"
            f"{completed.summary}\n\n"
            f"Artifacts: `{artifact_root}`"
        )
    body, _ = SecretRedactor().redact_text(body)

    try:
        resp = httpx.post(
            url,
            headers={"Authorization": f"token {settings.gitea_agent_token}"},
            json={"body": body},
            timeout=30,
        )
        resp.raise_for_status()
        return {"status": "posted", "comment_id": resp.json().get("id")}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
