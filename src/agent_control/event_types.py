"""Canonical Gitea webhook event type normalization."""

from __future__ import annotations

from typing import Any


def _workflow_status(payload: dict[str, Any]) -> str | None:
    run = payload.get("workflow_run") or payload.get("workflow_job") or {}
    conclusion = run.get("conclusion")
    if conclusion in ("success", "failure"):
        return conclusion
    status = run.get("status")
    if status in ("in_progress", "queued", "pending"):
        return "in_progress"
    if status == "completed" and conclusion:
        return conclusion
    action = payload.get("action")
    if action in ("completed", "finished"):
        return conclusion or "success"
    return None


def canonical_gitea_event_type(raw_event: str, payload: dict[str, Any]) -> tuple[str, str | None]:
    """Map Gitea X-Gitea-Event + payload to (canonical_type, raw_action)."""
    action = payload.get("action")

    if raw_event == "push":
        return "gitea.push", action

    if raw_event == "issue_comment":
        return "gitea.issue_comment", action or "created"

    if raw_event == "issues":
        if action == "opened":
            return "gitea.issue_opened", action
        if action == "labeled":
            return "gitea.issue_labeled", action
        return "gitea.issue_opened", action

    if raw_event == "issue_label":
        return "gitea.issue_labeled", action

    if raw_event == "pull_request":
        if action == "opened":
            return "gitea.pr_opened", action
        if action == "synchronize":
            return "gitea.pr_synchronized", action
        return "gitea.pr_opened", action

    if raw_event == "pull_request_sync":
        return "gitea.pr_synchronized", action

    if raw_event == "pull_request_comment":
        return "gitea.pr_comment", action or "created"

    if raw_event in ("workflow_run", "workflow_job"):
        wf_status = _workflow_status(payload)
        if wf_status == "failure":
            return "gitea.workflow_failed", action
        if wf_status == "success":
            return "gitea.workflow_passed", action
        return "gitea.workflow_started", action

    # Fallback: preserve raw name under gitea.* namespace
    return f"gitea.{raw_event.replace('.', '_')}", action
