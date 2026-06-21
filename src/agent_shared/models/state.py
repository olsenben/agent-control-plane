"""Verification state written by CT103 state reducer."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from agent_shared.models.intent import CommandIntent


class SafetyState(BaseModel):
    requires_manual_approval: bool = True


class VerificationState(BaseModel):
    schema_version: str = "verification_state.v1"
    project: str
    ref: str | None = None
    head_sha: str | None = None
    issue_state: dict[str, Any] = Field(default_factory=dict)
    pr_state: dict[str, Any] = Field(default_factory=dict)
    labels: list[str] = Field(default_factory=list)
    pipeline_status: str | None = None
    command_intent: CommandIntent | None = None
    snapshot_required: bool = False
    reduction_mode: str = "event_only"
    last_event_id: str | None = None
    last_event_type: str | None = None
    last_reduced_at: str | None = None
    event_count: int = 0
    dispatch_recommended: bool = False
    dispatch_kind: str | None = None
    pending_fix_request: dict[str, Any] | None = None
    active_approvals: dict[str, dict[str, Any]] = Field(default_factory=dict)
    last_policy_decision: str | None = None
    safety: SafetyState = Field(default_factory=SafetyState)
