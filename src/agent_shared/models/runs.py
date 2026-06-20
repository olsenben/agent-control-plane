"""Run metadata, results, and errors."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from agent_shared.constants import RiskClass, RunStatus
from agent_shared.models.plan import PlanResult
from agent_shared.models.review import ReviewResult


class AgentRunMetadata(BaseModel):
    schema_version: str = "agent_run.v1"
    run_id: str
    session_id: str
    workflow_id: str
    project: str
    flow: str
    agent: str
    risk_class: RiskClass | str
    workflow_definition: str
    flow_config_id: str
    flow_version: str
    trigger_event_id: str
    base_ref: str
    target_sha: str | None = None
    created_at: str
    status: RunStatus | str
    engine: str | None = None
    warnings: list[str] = Field(default_factory=list)


class RLMResult(BaseModel):
    schema_version: str = "rlm_result.v1"
    run_id: str
    session_id: str
    project: str
    flow: str
    agent: str
    risk_class: RiskClass | str
    workflow_definition: str
    flow_config_id: str
    flow_version: str
    status: str
    summary: str
    engine: str | None = None
    patch_path: str | None = None
    trace_path: str | None = None
    context_receipt_path: str | None = None
    verification_path: str | None = None
    requires_owner_approval: bool = False
    warnings: list[str] = Field(default_factory=list)
    review_result: ReviewResult | None = None
    plan_result: PlanResult | None = None


class AgentError(BaseModel):
    schema_version: str = "agent_error.v1"
    run_id: str
    stage: str
    error_type: str
    message: str
    recoverable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)
