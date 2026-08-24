"""Remote publish artifacts for Slice 6D / V4.1.1 brokerage."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Legacy 6D artifact publish_state (remote_publish_result.json)
LegacyPublishState = Literal[
    "planned",
    "dry_run_passed",
    "branch_published",
    "pr_opened",
    "publish_failed_partial",
    "publish_failed",
]

# V4.1.1 broker lifecycle (authoritative CT103 publish record)
BrokerPublishState = Literal[
    "not_requested",
    "queued",
    "validating",
    "rejected",
    "remote_pending",
    "succeeded",
    "failed_retryable",
    "failed_terminal",
]

# Back-compat alias used by existing RemotePublishResult
PublishState = LegacyPublishState

WorkerResultStatus = Literal[
    "patch_bundle_ready",
    "worker_rejected",
    "worker_failed",
]

FixStatus = Literal[
    "patch_bundle_ready",
    "local_patch_passed",  # legacy — treat as non-authoritative
    "publish_failed",
    "branch_published_pr_failed",
    "pr_opened_pending_ci",
    "ci_verified",
]


class RemotePublishResult(BaseModel):
    schema_version: str = "remote_publish_result.v1"
    publish_state: PublishState
    agent_branch: str
    base_ref: str
    head_commit_sha: str | None = None
    opened_pr_number: int | None = None
    opened_pr_url: str | None = None
    remote_branch_preexisting: bool = False
    existing_pr_reused: bool = False
    approved_base_sha: str | None = None
    dry_run: bool = False
    messages: list[str] = Field(default_factory=list)


class PublishRecord(BaseModel):
    """Authoritative CT103 publish lifecycle for one bundle."""

    schema_version: str = "publish_record.v1"
    run_id: str
    kind: str
    attempt_id: str
    bundle_id: str
    publish_state: BrokerPublishState = "not_requested"
    job_id: str | None = None
    expected_commit_sha: str | None = None
    commit_sha: str | None = None
    agent_branch: str | None = None
    pr_number: int | None = None
    pr_url: str | None = None
    trusted_base_sha: str | None = None
    patch_sha256: str | None = None
    result_tree_sha: str | None = None
    approval_id: str | None = None
    approval_target_id: str | None = None
    project: str | None = None
    messages: list[str] = Field(default_factory=list)
    updated_at: str | None = None


class PublishIntent(BaseModel):
    """Pre-push CI correlation intent (registered before remote mutation)."""

    schema_version: str = "publish_intent.v1"
    run_id: str
    bundle_id: str
    kind: str
    project: str
    agent_branch: str
    expected_commit_sha: str
    created_at: str
    activated: bool = False
    publish_effect_id: str | None = None
    transaction_id: str | None = None
    capability_id: str | None = None
    patch_digest: str | None = None
    source_sha: str | None = None
    intended_pr_title: str | None = None
