"""Admission decision, escalation, and feedback envelopes."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from agent_shared.models.transaction.identity import CompositeIdentity

AdmissionDecisionLabel = Literal["AUTO_ADMIT", "REJECT", "ESCALATE"]
RiskTier = Literal["R0", "R1", "R2", "R3", "UNKNOWN"]
ScopeRelation = Literal[
    "WITHIN_PREDICTED_SCOPE",
    "OUTSIDE_SCOPE_BUT_EVIDENCE_RELATED",
    "OUTSIDE_SCOPE_LOCAL_CREATION",
    "OUTSIDE_SCOPE_HIGH_RISK",
    "UNEXPLAINED",
    "SELECTED_SCOPE_UNAVAILABLE",
]
AdmissionArm = Literal[
    "PREWRITE_SCOPE_EQUIVALENT",
    "STATIC_POSTHOC_SCOPE_GATE",
    "TRANSACTIONAL_RELATIONAL_ADMISSION",
    "BROAD_PUBLISH_BASELINE",
]


class PolicyFields(BaseModel):
    """Required on every production admission decision."""

    model_config = ConfigDict(extra="forbid")

    policy_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    admission_implementation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class TaskRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1)
    task_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_task_id: str | None = None


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bundle_id: str = Field(min_length=1)
    bundle_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class PatchAdmissionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["patch_admission_decision.v1"] = "patch_admission_decision.v1"
    proposal_id: str
    arm: AdmissionArm = "TRANSACTIONAL_RELATIONAL_ADMISSION"
    decision: AdmissionDecisionLabel
    reasons: list[str] = Field(default_factory=list)
    risk_tier: RiskTier
    scope_relation: ScopeRelation
    evidence_classes: list[str] = Field(default_factory=list)
    verification: dict[str, Any] = Field(default_factory=dict)
    durable_capability: dict[str, Any] | None = None
    admission_latency_ms: float | None = None
    decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    admission_implementation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    tenant_id: str | None = None
    org_id: str | None = None
    repository: str | None = None


class AdmissionEscalation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["admission_escalation.v1"] = "admission_escalation.v1"
    escalation_id: str = Field(min_length=1)
    decision_id: str | None = None
    proposal_id: str | None = None
    tenant_id: str = Field(min_length=1)
    org_id: str = Field(min_length=1)
    repository: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    source_sha: str = Field(min_length=7)
    patch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    task: TaskRef
    evidence: EvidenceRef
    reasons: list[str] = Field(min_length=1)
    policy: PolicyFields
    risk_classification: RiskTier
    auto_mint_capability: Literal[False] = False
    identity: CompositeIdentity
    created_at: str | None = None
    notes: str | None = None


class AdmissionFeedbackRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["admission_feedback_record.v1"] = "admission_feedback_record.v1"
    record_id: str = Field(min_length=1)
    proposal_id: str = Field(min_length=1)
    task_id: str | None = None
    repository: str = Field(min_length=1)
    source_sha: str = Field(min_length=7)
    patch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    bundle_id: str = Field(min_length=1)
    run_id: str | None = None
    arm: str | None = None
    captured_at: str = Field(min_length=1)
    learning_enabled: Literal[False] = False
    actor_memory_write: Literal[False] = False
    recursive_context_write: Literal[False] = False
    controller: Literal["TRANSACTIONAL_RELATIONAL_ADMISSION"] = (
        "TRANSACTIONAL_RELATIONAL_ADMISSION"
    )
    controller_hash: Literal[
        "ad265893a9e7161ba8acd0c95e778738d92584eb310cb6bac85e89121f72098c"
    ] = "ad265893a9e7161ba8acd0c95e778738d92584eb310cb6bac85e89121f72098c"
    decision: Literal["AUTO_ADMIT", "REJECT", "ESCALATE", "NOT_RUN"]
    reasons: list[str] = Field(default_factory=list)
    projection: dict[str, Any] | None = None
    conflict_codes: list[Literal["EVIDENCE_CONFLICT"]] = Field(default_factory=list)
    notes: str | None = None
    feeds_controller: Literal[False] = False
    tenant_id: str | None = None
    org_id: str | None = None
