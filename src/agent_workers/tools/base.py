"""ExecutionTool protocol and request/result types."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field

from agent_shared.constants import RiskClass
from agent_workers.artifacts.session_events import SessionEventWriter


class ToolRequest(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None


class ToolResult(BaseModel):
    tool: str
    request_id: str
    status: str
    output: dict[str, Any] = Field(default_factory=dict)
    artifact_paths: list[str] = Field(default_factory=list)


class ExecutionTool(Protocol):
    name: str
    risk_classes: set[RiskClass]

    def run(
        self,
        *,
        request: ToolRequest,
        workspace_path: str,
        policy: dict[str, Any],
        session: SessionEventWriter,
    ) -> ToolResult: ...
