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


# --- Slice 6F.1 failure evidence ---

EvidenceStatus = Literal["collected", "unavailable", "contract_mismatch"]
FailureClass = Literal[
    "test_failure",
    "lint_failure",
    "build_failure",
    "deterministic_typecheck_failure",
    "runner_unavailable",
    "infrastructure_failure",
    "checkout_failure",
    "dependency_registry_unavailable",
    "api_unavailable",
    "cancelled_or_superseded",
    "sandbox_failure",
    "unknown",
]

AUTO_REPAIRABLE_FAILURE_CLASSES: frozenset[str] = frozenset(
    {
        "test_failure",
        "lint_failure",
        "build_failure",
        "deterministic_typecheck_failure",
    }
)

REDACTION_POLICY_VERSION = "ci_log_redaction.v1"
TRUNCATION_STRATEGY = "head_error_windows_tail.v1"


class EvidenceJobRecord(BaseModel):
    job_id: str
    name: str = ""
    status: str = ""
    conclusion: str = ""
    retained_path: str = ""
    retained_sha256: str = ""
    bytes_retained: int = 0
    lines_retained: int = 0
    window_offsets: list[tuple[int, int]] = Field(default_factory=list)


class FailureEvidenceManifest(BaseModel):
    schema_version: str = "ci_failure_evidence.v1"
    evidence_observation_id: str
    status: EvidenceStatus
    fix_run_id: str
    repository: str
    expected_head_commit_sha: str
    pr_number: int | None = None
    workflow_run_id: str
    run_number: int | None = None
    workflow_run_attempt: int = 1
    workflow_path: str = ""
    workflow_display_name: str = ""
    redaction_policy_version: str = REDACTION_POLICY_VERSION
    redaction_count: int = 0
    bytes_received: int = 0
    bytes_retained: int = 0
    lines_retained: int = 0
    truncation_strategy: str = TRUNCATION_STRATEGY
    retained_sha256: str = ""
    source_content_length: int | None = None
    jobs: list[EvidenceJobRecord] = Field(default_factory=list)
    failure_class: FailureClass = "unknown"
    reason_codes: list[str] = Field(default_factory=list)
    collected_at: str = ""
    has_terminal_failed_job: bool = False


class FixCiFailureEvidenceCollectedEvent(BaseModel):
    schema_version: str = "agent_fix_ci_failure_evidence_collected.v1"
    type: str = "agent.fix_ci_failure_evidence_collected"
    fix_run_id: str
    repository: str
    expected_head_commit_sha: str
    pr_number: int | None = None
    evidence_observation_id: str
    workflow_run_id: str
    workflow_run_attempt: int = 1
    status: EvidenceStatus = "collected"
    failure_class: FailureClass = "unknown"
    has_terminal_failed_job: bool = False


class FixCiFailureEvidenceUnavailableEvent(BaseModel):
    schema_version: str = "agent_fix_ci_failure_evidence_unavailable.v1"
    type: str = "agent.fix_ci_failure_evidence_unavailable"
    fix_run_id: str
    repository: str
    expected_head_commit_sha: str
    pr_number: int | None = None
    evidence_observation_id: str
    workflow_run_id: str
    workflow_run_attempt: int = 1
    status: EvidenceStatus
    reason_codes: list[str] = Field(default_factory=list)


# --- Slice 6F.2 repair lineage ---

class FixCiRepairRequestedEvent(BaseModel):
    schema_version: str = "agent_fix_ci_repair_requested.v1"
    type: str = "agent.fix_ci_repair_requested"
    fix_run_id: str
    repository: str
    expected_head_commit_sha: str
    pr_number: int | None = None
    evidence_observation_id: str
    repair_attempt: int
    repair_key: str = ""


class FixCiRepairBlockedEvent(BaseModel):
    schema_version: str = "agent_fix_ci_repair_blocked.v1"
    type: str = "agent.fix_ci_repair_blocked"
    fix_run_id: str
    repository: str
    expected_head_commit_sha: str
    pr_number: int | None = None
    reason_codes: list[str] = Field(default_factory=list)
    label: str = "agent:blocked"


class FixCiRepairStartedEvent(BaseModel):
    schema_version: str = "agent_fix_ci_repair_started.v1"
    type: str = "agent.fix_ci_repair_started"
    fix_run_id: str
    repository: str
    expected_head_commit_sha: str
    pr_number: int | None = None
    repair_attempt: int
    repair_key: str = ""


class FixCiRepairPushedEvent(BaseModel):
    schema_version: str = "agent_fix_ci_repair_pushed.v1"
    type: str = "agent.fix_ci_repair_pushed"
    fix_run_id: str
    repository: str
    previous_head_commit_sha: str
    new_head_commit_sha: str
    pr_number: int | None = None
    repair_attempt: int
    repair_key: str = ""


class FixCiRepairExhaustedEvent(BaseModel):
    schema_version: str = "agent_fix_ci_repair_exhausted.v1"
    type: str = "agent.fix_ci_repair_exhausted"
    fix_run_id: str
    repository: str
    expected_head_commit_sha: str
    pr_number: int | None = None
    repair_attempt: int
    max_attempts: int = 1


class FixCiRepairStaleEvent(BaseModel):
    schema_version: str = "agent_fix_ci_repair_stale.v1"
    type: str = "agent.fix_ci_repair_stale"
    fix_run_id: str
    repository: str
    expected_head_commit_sha: str
    pr_number: int | None = None
    repair_attempt: int = 0
    repair_key: str = ""
    reason: str = "remote_head_changed"
    observed_head_commit_sha: str | None = None
