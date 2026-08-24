"""task_envelope.v1 and security_finding.v1 models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_shared.hash_utils import canonical_json_hash
from agent_shared.models.transaction.identity import CompositeIdentity, IdentityPrincipal

TaskProvider = Literal["GITEA_ISSUE", "SECURITY_FINDING_FIXTURE", "OTHER_TYPED"]
TaskType = Literal[
    "SECURITY_REMEDIATION",
    "FUNCTIONAL_MAINTENANCE",
    "DEPENDENCY",
    "PUBLIC_API",
    "CONFIG",
    "OTHER_TYPED",
]
ChangeClass = Literal[
    "PRODUCTION_SOURCE_CHANGE",
    "SECURITY_FINDING_TASK",
    "DEPENDENCY_MANIFEST_CHANGE",
    "SECURITY_SENSITIVE_SYMBOL_OR_CONFIG",
    "PUBLIC_API_CHANGE",
    "LOCAL_PRIVATE_CHANGE",
    "OTHER_TYPED",
]
FindingSeverity = Literal["NONE", "NOTE", "WARNING", "ERROR", "CRITICAL", "UNKNOWN"]


class PolicyContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    admission_implementation_digest: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )


class RequestedChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1)
    title: str | None = None


class TaskEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["task_envelope.v1"] = "task_envelope.v1"
    task_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    org_id: str = Field(min_length=1)
    repository: str = Field(min_length=1)
    source_sha: str = Field(min_length=7)
    task_provider: TaskProvider
    provider_task_id: str = Field(min_length=1)
    human_initiator: IdentityPrincipal
    initiator_identity: str = Field(min_length=1)
    identity: CompositeIdentity | None = None
    task_type: TaskType
    requested_change: RequestedChange
    authorized_change_classes: list[ChangeClass] = Field(default_factory=list)
    authorized_files: list[str] = Field(default_factory=list)
    authorized_surfaces: list[str] = Field(default_factory=list)
    security_finding_ids: list[str] = Field(default_factory=list)
    policy_context: PolicyContext
    created_at: str = Field(min_length=1)
    task_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    notes: str | None = None

    @model_validator(mode="after")
    def _initiator_matches(self) -> TaskEnvelope:
        if self.human_initiator.principal_kind != "HUMAN_INITIATOR":
            raise ValueError("human_initiator.principal_kind must be HUMAN_INITIATOR")
        if self.initiator_identity != self.human_initiator.identity_id:
            raise ValueError("initiator_identity must match human_initiator.identity_id")
        return self


class FindingLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    symbol: str | None = None


class FindingProducer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    principal_kind: Literal["EVIDENCE_PROVIDER"] = "EVIDENCE_PROVIDER"
    identity_id: str = Field(min_length=1)
    producer_id: str = Field(min_length=1)
    producer_version: str = Field(min_length=1)
    issuer: str | None = None
    namespace: str | None = None


class FindingEvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=1)
    evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_type: str | None = None
    raw_artifact_location: str | None = None
    notes: str | None = None


class SecurityFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["security_finding.v1"] = "security_finding.v1"
    tenant_id: str = Field(min_length=1)
    org_id: str = Field(min_length=1)
    repository: str = Field(min_length=1)
    producer: FindingProducer
    finding_id: str = Field(min_length=1)
    rule_id: str = Field(min_length=1)
    cwe: str | None = None
    source_sha: str = Field(min_length=7)
    affected_location: FindingLocation
    severity: FindingSeverity
    finding_evidence: list[FindingEvidenceRef] = Field(min_length=1)
    notes: str | None = None


def task_digest_for(payload: dict[str, Any]) -> str:
    body = {key: value for key, value in payload.items() if key != "task_digest"}
    return canonical_json_hash(body)
