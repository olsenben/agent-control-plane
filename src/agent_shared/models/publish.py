"""Remote publish artifacts for Slice 6D."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PublishState = Literal[
    "planned",
    "dry_run_passed",
    "branch_published",
    "pr_opened",
    "publish_failed_partial",
    "publish_failed",
]

FixStatus = Literal[
    "local_patch_passed",
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
