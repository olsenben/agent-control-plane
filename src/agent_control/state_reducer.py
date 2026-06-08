"""Event-only and snapshot-aware state reduction."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ReductionMode(str, Enum):
    EVENT_ONLY = "event_only"
    SNAPSHOT_AWARE = "snapshot_aware"


class LogicalState(BaseModel):
    project: str
    ref: str | None = None
    head_sha: str | None = None
    issue_state: dict[str, Any] = Field(default_factory=dict)
    pr_state: dict[str, Any] = Field(default_factory=dict)
    labels: list[str] = Field(default_factory=list)
    pipeline_status: str | None = None
    command_intent: str | None = None
    snapshot_required: bool = False
    reduction_mode: ReductionMode = ReductionMode.EVENT_ONLY
    last_event_id: str | None = None
    last_event_type: str | None = None
    last_reduced_at: str | None = None
    event_count: int = 0


def _label_names(payload: dict[str, Any]) -> list[str]:
    issue = payload.get("issue") or {}
    label = payload.get("label")
    labels: list[str] = []
    if label and label.get("name"):
        labels.append(label["name"])
    for item in issue.get("labels") or []:
        if isinstance(item, dict) and item.get("name"):
            labels.append(item["name"])
    return labels


def reduce_event_only(events: list[dict[str, Any]], project: str) -> LogicalState:
    """Update logical state from normalized events without a local checkout."""
    state = LogicalState(project=project, reduction_mode=ReductionMode.EVENT_ONLY)
    for event in events:
        etype = event.get("type", "")
        payload = event.get("payload", {})

        if etype == "gitea.push":
            state.ref = payload.get("ref")
            state.head_sha = payload.get("after")

        elif etype == "gitea.issue_opened":
            issue = payload.get("issue") or {}
            state.issue_state = {
                "number": issue.get("number"),
                "title": issue.get("title"),
                "state": issue.get("state"),
            }

        elif etype == "gitea.issue_labeled":
            state.labels = _label_names(payload)

        elif etype in ("gitea.issue_comment", "gitea.pr_comment"):
            body = payload.get("comment", {}).get("body", "")
            if "/agent review" in body:
                state.command_intent = "review"
            elif "/agent fix" in body:
                state.command_intent = "fix"

        elif etype == "gitea.pr_opened":
            pr = payload.get("pull_request") or {}
            state.pr_state = {
                "number": pr.get("number"),
                "title": pr.get("title"),
                "state": pr.get("state"),
            }
            state.ref = pr.get("head", {}).get("ref") or pr.get("base", {}).get("ref")
            state.head_sha = pr.get("head", {}).get("sha")

        elif etype == "gitea.pr_synchronized":
            state.snapshot_required = True
            pr = payload.get("pull_request") or {}
            state.ref = pr.get("head", {}).get("ref") or state.ref
            state.head_sha = pr.get("head", {}).get("sha") or state.head_sha

        elif etype.startswith("gitea.workflow_"):
            state.pipeline_status = etype.replace("gitea.workflow_", "")

    return state
