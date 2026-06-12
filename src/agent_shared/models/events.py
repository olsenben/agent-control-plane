"""CT104 result events and session log lines."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AgentRunCompletedEvent(BaseModel):
    schema_version: str = "agent_run_completed.v1"
    source: str = "ct104"
    type: str = "agent.run_completed"
    run_id: str
    job_id: str
    workflow_id: str
    session_id: str
    trigger_event_id: str
    trigger_delivery_id: str | None = None
    project: str
    flow: str
    agent: str
    risk_class: str
    status: str
    summary: str
    artifact_root: str


class SessionEvent(BaseModel):
    ts: str
    run_id: str
    event: str
    request_id: str | None = None
    tool: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    status: str | None = None
    bytes: int | None = None
    redacted_secrets: int | None = None
    message: str | None = None
    content: str | None = None
    is_complete: bool | None = None
    artifact: str | None = None
    reason: str | None = None
