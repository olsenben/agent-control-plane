"""CI verification models (Slice 6E.1)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CiVerdict = Literal["pending", "verified", "failing", "superseded", "expired"]
ApiVerificationStatus = Literal["confirmed", "contradicted", "unavailable", "skipped"]
NormalizedConclusion = Literal[
    "success",
    "failure",
    "cancelled",
    "timed_out",
    "skipped",
    "unknown",
]


class RequiredWorkflow(BaseModel):
    workflow_id: str | None = None
    path: str = ""
    display_name: str = ""
    source: str = "matrix"  # matrix | repo_default | config


class WorkflowObservation(BaseModel):
    workflow_id: str | None = None
    path: str = ""
    display_name: str = ""
    workflow_run_id: str
    run_attempt: int = 1
    status: str = ""
    conclusion: NormalizedConclusion = "unknown"
    head_sha: str = ""
    pr_number: int | None = None
    delivery_id: str | None = None
    observed_at: str = ""
    api_verification_status: ApiVerificationStatus = "skipped"


class CiVerificationResult(BaseModel):
    schema_version: str = "ci_verification_result.v1"
    fix_run_id: str
    repository: str
    expected_head_commit_sha: str
    verdict: CiVerdict = "pending"
    required_workflows: list[RequiredWorkflow] = Field(default_factory=list)
    observations: list[WorkflowObservation] = Field(default_factory=list)
    missing_workflows: list[str] = Field(default_factory=list)
    evaluated_at: str = ""
    reason_codes: list[str] = Field(default_factory=list)
    verdict_revision: int = 0
    opened_pr_number: int | None = None
    issue_id: int | None = None


class PendingCiRecord(BaseModel):
    """Immutable-ish pending index entry keyed by repo + exact head SHA."""

    schema_version: str = "pending_ci.v1"
    fix_run_id: str
    repository: str
    expected_head_commit_sha: str
    opened_pr_number: int | None = None
    issue_id: int | None = None
    agent_branch: str | None = None
    required_workflows: list[RequiredWorkflow] = Field(default_factory=list)
    created_at: str = ""
    superseded_by_sha: str | None = None
    expired_at: str | None = None
    current_verdict: CiVerdict = "pending"
    verdict_revision: int = 0
    artifact_root: str | None = None


class FixCiObservedEvent(BaseModel):
    schema_version: str = "agent_fix_ci_observed.v1"
    type: str = "agent.fix_ci_observed"
    fix_run_id: str
    repository: str
    expected_head_commit_sha: str
    observation: WorkflowObservation
    delivery_id: str | None = None


class FixCiVerdictChangedEvent(BaseModel):
    schema_version: str = "agent_fix_ci_verdict_changed.v1"
    type: str = "agent.fix_ci_verdict_changed"
    fix_run_id: str
    repository: str
    expected_head_commit_sha: str
    previous_verdict: CiVerdict
    verdict: CiVerdict
    verdict_revision: int
    reason_codes: list[str] = Field(default_factory=list)
    evaluated_at: str = ""
