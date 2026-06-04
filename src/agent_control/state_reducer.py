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


def reduce_event_only(events: list[dict[str, Any]], project: str) -> LogicalState:
    """Update logical state from normalized events without a local checkout."""
    state = LogicalState(project=project, reduction_mode=ReductionMode.EVENT_ONLY)
    for event in events:
        etype = event.get("type", "")
        payload = event.get("payload", {})
        if etype == "gitea.push":
            state.ref = payload.get("ref")
            state.head_sha = payload.get("after")
        elif etype in ("gitea.issue_comment", "gitea.pr_comment"):
            body = payload.get("comment", {}).get("body", "")
            if "/agent review" in body:
                state.command_intent = "review"
            elif "/agent fix" in body:
                state.command_intent = "fix"
        elif etype == "gitea.pr_synchronized":
            state.snapshot_required = True
        elif etype.startswith("gitea.workflow_"):
            state.pipeline_status = etype.replace("gitea.workflow_", "")
    return state
