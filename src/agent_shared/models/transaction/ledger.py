"""software_transaction.v1, graph edge, and attestation envelopes."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from agent_shared.models.transaction.admission import EvidenceRef, TaskRef
from agent_shared.models.transaction.identity import CompositeIdentity, IdentityPrincipal

DurableOutcome = Literal[
    "AUTO_ADMITTED_CAPABILITY_MINTED",
    "ESCALATED_NO_CAPABILITY",
    "REJECTED_NO_CAPABILITY",
    "PUBLISHED",
    "VERIFICATION_PASSED",
    "VERIFICATION_FAILED",
    "VERIFICATION_MISSING",
    "TRANSACTION_FINALIZED",
    "OTHER_TYPED",
]
TransactionControlEventType = Literal[
    "PUBLISH_REQUESTED",
    "RUN_CANCELLED",
    "REFUSED_CANCELLED_RUN",
    "RUN_TIMED_OUT",
    "REFUSED_TIMED_OUT_RUN",
    "STUCK_TRANSACTION",
    "RETRY_EXHAUSTED",
    "RECONCILE_BEFORE_RETRY",
    "ALREADY_APPLIED",
]
GraphEdgeType = Literal[
    "HUMAN_INITIATED_TASK",
    "TASK_CREATED_SESSION",
    "SESSION_PRODUCED_PATCH",
    "PATCH_CHANGED_SYMBOL",
    "PATCH_RESOLVED_FINDING",
    "PATCH_INTRODUCED_FINDING",
    "EVIDENCE_SUPPORTS_PATCH",
    "POLICY_GOVERNED_DECISION",
    "DECISION_MINTED_CAPABILITY",
    "CAPABILITY_PUBLISHED_PR",
    "PR_RECEIVED_CI_VERDICT",
    "HUMAN_OVERRULED_DECISION",
    "TRANSACTION_FINALIZED_AS",
]
EntityKind = Literal[
    "HUMAN",
    "TASK",
    "SESSION",
    "PATCH",
    "SYMBOL",
    "FINDING",
    "EVIDENCE",
    "POLICY",
    "DECISION",
    "CAPABILITY",
    "PR",
    "CI_VERDICT",
    "TRANSACTION",
    "HUMAN_DECISION",
]


class ActorRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str | None = None
    actor_identity: IdentityPrincipal
    worker_identity: IdentityPrincipal


class PatchRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str | None = None
    source_sha: str = Field(min_length=7)
    patch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class DecisionRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["AUTO_ADMIT", "REJECT", "ESCALATE"]
    decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    escalation_id: str | None = None


class CapabilityRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability_id: str | None = None
    admission_decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    capability_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class SoftwareTransaction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["software_transaction.v1"] = "software_transaction.v1"
    transaction_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    org_id: str = Field(min_length=1)
    repository: str = Field(min_length=1)
    task: TaskRef
    actor: ActorRef
    patch: PatchRef
    evidence: EvidenceRef
    decision: DecisionRef
    capability: CapabilityRef | None = None
    durable_outcome: DurableOutcome
    identity: CompositeIdentity
    recorded_at: str = Field(min_length=1)
    append_only: Literal[True] = True
    event_seq: int = Field(ge=0)
    notes: str | None = None
    event_id: str | None = None
    event_type: str | None = None
    component: str | None = None
    principal: IdentityPrincipal | None = None
    timestamp: str | None = None
    code_revision: str | None = None
    policy_revision: str | None = None
    payload_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class TransactionGraphEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["transaction_graph_edge.v1"] = "transaction_graph_edge.v1"
    edge_id: str = Field(min_length=1)
    edge_type: GraphEdgeType
    from_entity_id: str = Field(min_length=1)
    from_entity_kind: EntityKind
    to_entity_id: str = Field(min_length=1)
    to_entity_kind: EntityKind
    tenant_id: str = Field(min_length=1)
    org_id: str = Field(min_length=1)
    repository: str = Field(min_length=1)
    transaction_id: str | None = None
    captured_at: str = Field(min_length=1)
    used_for_live_decision: Literal[False] = False
    identity: CompositeIdentity | None = None
    notes: str | None = None


class SourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_sha: str = Field(min_length=7)
    source_tree_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class AttestationPatchRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str | None = None
    patch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class AttestationPolicyRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    admission_implementation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class PublishReceiptRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    receipt_id: str = Field(min_length=1)
    receipt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class CiOutcomeRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal[
        "verification_requested",
        "verification_passed",
        "verification_failed",
        "verification_missing",
    ]
    verifier_identity: IdentityPrincipal | None = None
    outcome_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class SoftwareTransactionAttestation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["software_transaction_attestation.v1"] = (
        "software_transaction_attestation.v1"
    )
    attestation_id: str = Field(min_length=1)
    transaction_id: str | None = None
    tenant_id: str = Field(min_length=1)
    org_id: str = Field(min_length=1)
    repository: str = Field(min_length=1)
    task: TaskRef
    source: SourceRef
    patch: AttestationPatchRef
    actor: ActorRef
    evidence_bundle: EvidenceRef
    policy: AttestationPolicyRef
    admission_decision: DecisionRef
    capability: CapabilityRef | None = None
    publish_receipt: PublishReceiptRef | None = None
    ci_outcome: CiOutcomeRef | None = None
    identity: CompositeIdentity
    hash_algorithm: Literal["sha256"] = "sha256"
    attestation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    sigstore: Literal[False] = False
    public_transparency_log: Literal[False] = False
    issued_at: str | None = None
    notes: str | None = None


class TransactionControlEvent(BaseModel):
    """Operability ledger event. Additive; does not replace software_transaction.v1."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["transaction_control_event.v1"] = "transaction_control_event.v1"
    event_id: str = Field(min_length=1)
    transaction_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    component: str = Field(min_length=1)
    principal: IdentityPrincipal | None = None
    timestamp: str = Field(min_length=1)
    code_revision: str | None = None
    policy_revision: str | None = None
    payload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload: dict[str, Any] = Field(default_factory=dict)
    repository: str | None = None
    run_id: str | None = None
