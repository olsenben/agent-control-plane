"""CT104 result events and session log lines."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from agent_shared.models.fix import FixResult
from agent_shared.models.plan import PlanResult
from agent_shared.models.review import ReviewResult

PromptHashSource = Literal["final_prompt", "not_available"]


class RiskTagSourceEntry(BaseModel):
    tag: str
    source: Literal["model_output", "policy_gate", "semgrep", "human"] = "model_output"


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
    terminal_status: str | None = None
    summary: str
    artifact_root: str
    command_kind: str | None = None
    repo_full_name: str | None = None
    issue_id: int | None = None
    pr_id: int | None = None
    branch: str | None = None
    commit_sha: str | None = None
    review_result: ReviewResult | None = None
    plan_result: PlanResult | None = None
    fix_result: FixResult | None = None
    patch_path: str | None = None
    context_sources: list[str] = Field(default_factory=list)
    prompt_hash: str | None = None
    prompt_hash_source: PromptHashSource = "not_available"
    summary_hash: str | None = None
    engine: str | None = None
    model_policy: str | None = None
    risk_tags: list[str] = Field(default_factory=list)
    risk_tag_sources: list[RiskTagSourceEntry] = Field(default_factory=list)
    policy_decision: Literal["allow", "deny", "pending_approval"] = "allow"
    approval_target_id: str | None = None
    plan_alias: str | None = None
    plan_hash: str | None = None
    blast_radius_hash: str | None = None
    diff_gate_passed: bool | None = None
    diff_gate_violation_codes: list[str] = Field(default_factory=list)
    diff_gate_policy_sources: list[str] = Field(default_factory=list)
    approval_id: str | None = None
    fix_status: str | None = None
    agent_branch: str | None = None
    head_commit_sha: str | None = None
    opened_pr_number: int | None = None
    opened_pr_url: str | None = None
    approved_base_sha: str | None = None
    publish_state: str | None = None
    # V4.1.1 patch-bundle producer fields
    producer_protocol: str | None = None
    bundle_id: str | None = None
    attempt_id: str | None = None
    bundle_kind: str | None = None
    worker_result: str | None = None


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
