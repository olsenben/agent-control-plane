"""Scoped approval records for Risk 2 fix (Slice 6A plan-scoped handles)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ApprovalStatus = Literal[
    "approved",
    "rejected",
    "expired",
    "reserved",
    "claimed",
    "consumed",
]


class WorkItemApproval(BaseModel):
    """Plan-scoped approval handle in Slice 6A — not a durable epic WorkItem."""

    schema_version: str = "work_item_approval.v1"
    approval_id: str
    approval_target_id: str
    plan_alias: str
    plan_run_id: str
    plan_hash: str
    blast_radius_hash: str
    project: str
    issue_id: int
    allowed_files: list[str] = Field(default_factory=list)
    allowed_commands: list[str] = Field(default_factory=lambda: ["fix"])
    risk_class: str = "write_patch"
    approved_by_login: str
    approved_at: str
    expires_at: str
    status: ApprovalStatus = "approved"
    reject_reason: str | None = None
    source_comment_id: int | None = None
    source_event_id: str | None = None
    source_url: str | None = None
    approval_command_text_hash: str | None = None
    approved_base_sha: str | None = None
    approved_base_ref: str | None = None
    policy_source_sha: str | None = None
    reserved_at: str | None = None
    reserved_by_fix_run_id: str | None = None
    claimed_at: str | None = None
    claimed_by_publish_job_id: str | None = None
    publish_state: str | None = None
    consumed_at: str | None = None
    consumed_by_run_id: str | None = None
    consumed_event_id: str | None = None


class ApprovalRejected(BaseModel):
    schema_version: str = "approval_rejected.v1"
    approval_target_id: str
    plan_run_id: str | None = None
    plan_alias: str | None = None
    project: str
    issue_id: int
    rejected_by_login: str
    rejected_at: str
    reject_reason: str | None = None
    source_comment_id: int | None = None
    source_event_id: str | None = None


class FixRequestedEvent(BaseModel):
    schema_version: str = "fix_requested.v1"
    approval_target_id: str
    project: str
    issue_id: int
    policy_decision: Literal["blocked", "approved"]
    reason: str | None = None
    requested_by_login: str | None = None


class FixAuthorizedEvent(BaseModel):
    schema_version: str = "fix_authorized.v1"
    dry_run: bool = False
    worker_enqueued: bool = False
    dispatch_target: str = "none"
    next_slice: str = "6B"
    fix_run_id: str | None = None
    approval_id: str
    approval_target_id: str
    plan_run_id: str
    plan_hash: str
    blast_radius_hash: str
    project: str
    issue_id: int


class ApprovalConsumedEvent(BaseModel):
    schema_version: str = "approval_consumed.v1"
    approval_id: str
    approval_target_id: str
    plan_run_id: str
    project: str
    issue_id: int
    consumed_by_fix_run_id: str
    consumed_by_event_id: str | None = None


class ApprovalReservedEvent(BaseModel):
    schema_version: str = "approval_reserved.v1"
    approval_id: str
    approval_target_id: str
    plan_run_id: str
    project: str
    issue_id: int
    reserved_by_fix_run_id: str


class ApprovalReleasedEvent(BaseModel):
    schema_version: str = "approval_released.v1"
    approval_id: str
    approval_target_id: str
    plan_run_id: str
    project: str
    issue_id: int
    released_by_fix_run_id: str
    reason: str


class FixEnqueuedEvent(BaseModel):
    schema_version: str = "fix_enqueued.v1"
    fix_run_id: str
    job_id: str
    approval_id: str
    approval_target_id: str
    plan_run_id: str
    project: str
    issue_id: int
    worker_enqueued: bool = True
    dispatch_target: str = "rlm-root"
    approval_reserved: bool = True


class FixPlanStepBinding(BaseModel):
    id: str
    summary: str = ""
    files: list[str] = Field(default_factory=list)


class FixAuthorizationBinding(BaseModel):
    """Compact immutable approval scope for CT104 fix jobs (Slice 6B)."""

    schema_version: str = "fix_authorization_binding.v1"
    approval_id: str
    approval_target_id: str
    plan_run_id: str
    plan_hash: str
    blast_radius_hash: str
    allowed_files: list[str] = Field(default_factory=list)
    plan_summary: str = ""
    plan_steps: list[FixPlanStepBinding] = Field(default_factory=list)
    ci_hints: list[str] = Field(default_factory=list)
    approved_base_sha: str | None = None
    approved_base_ref: str | None = None
    policy_source_sha: str | None = None
