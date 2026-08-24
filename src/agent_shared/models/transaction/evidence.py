"""Evidence provider, route, and bundle envelopes."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

TrustClass = Literal[
    "AUTHORITATIVE_CONTROL_PLANE",
    "AUTHORITATIVE_CI",
    "CONFIGURED_SECURITY_TOOL",
    "TASK_SYSTEM",
    "REPOSITORY_METADATA",
    "ADVISORY_TOOL",
    "ACTOR_PROVIDED",
    "UNKNOWN",
]
RequirementClass = Literal["REQUIRED_PROVIDER", "OPTIONAL_PROVIDER"]
AdapterClass = Literal[
    "SAST",
    "SECURITY_TEST",
    "SECURITY_POC",
    "TASK_EVIDENCE",
    "SECRET_SCAN",
    "DEPENDENCY_SCAN",
    "CONFIG_POLICY",
    "FUNCTIONAL_TEST",
    "CI_VERDICT",
    "OTHER_TYPED",
]
EvidenceType = Literal[
    "FUNCTIONAL_TEST",
    "SECURITY_TEST",
    "SECURITY_POC",
    "SAST",
    "SECRET_SCAN",
    "DEPENDENCY_SCAN",
    "CONFIG_POLICY",
    "TASK_REQUIREMENT",
    "SECURITY_FINDING",
    "REPOSITORY_POLICY",
    "OWNERSHIP_POLICY",
    "SEMANTIC_RELATION",
    "CI_VERDICT",
    "OTHER_TYPED",
]
ChangeClass = Literal[
    "PRODUCTION_SOURCE_CHANGE",
    "SECURITY_FINDING_TASK",
    "DEPENDENCY_MANIFEST_CHANGE",
    "SECURITY_SENSITIVE_SYMBOL_OR_CONFIG",
    "PUBLIC_API_CHANGE",
]
IncompleteReason = Literal[
    "TOOL_FAILURE",
    "TIMEOUT",
    "UNSUPPORTED",
    "MALFORMED",
    "MISSING_REQUIRED_CLASS",
    "UNBOUND",
    "STALE",
    "EVIDENCE_CONFLICT",
    "NOT_RUN",
]


class ProviderIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    principal_kind: Literal["EVIDENCE_PROVIDER"] = "EVIDENCE_PROVIDER"
    identity_id: str = Field(min_length=1)
    issuer: str | None = None
    namespace: str | None = None


class InterchangeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: str = Field(min_length=1)
    version: str = Field(min_length=1)
    vendor_neutral: bool
    native_fallback: str | None = None
    notes: str | None = None


class RepositoryScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope_kind: Literal["ALL_CONFIGURED", "REPOSITORY_LIST"]
    repositories: list[str] = Field(default_factory=list)


class EvidenceProvider(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["evidence_provider.v1"] = "evidence_provider.v1"
    provider_id: str = Field(min_length=1)
    provider_identity: ProviderIdentity
    adapter_id: str = Field(min_length=1)
    adapter_class: AdapterClass
    producer_id: str = Field(min_length=1)
    producer_version: str = Field(min_length=1)
    version: str = Field(min_length=1)
    interchange: InterchangeSpec
    evidence_types: list[EvidenceType] = Field(min_length=1)
    trust_class: TrustClass
    requirement_class: RequirementClass
    repository_scope: RepositoryScope
    timeout_ms: int = Field(ge=1)
    trust_inferred_from_format: Literal[False] = False
    binding_required: bool
    baseline_and_candidate_required: bool
    imports_admission_controller: Literal[False] = False
    llm_parser: Literal[False] = False
    hidden_gold: Literal[False] = False
    learned_judge: Literal[False] = False
    missing_output_status: Literal["TOOL_FAILURE", "INCOMPLETE"] = "TOOL_FAILURE"
    authoritative_when_actor_provided: Literal[False] = False
    notes: str | None = None


RouteReason = Literal[
    "TASK_TYPE_SECURITY_REMEDIATION",
    "PATCH_TOUCHES_SECURITY_SENSITIVE_CLASS",
    "REPO_POLICY_REQUIRES_SAST",
]


class RoutedProvider(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str = Field(min_length=1)
    requirement_class: RequirementClass
    reasons: list[RouteReason] = Field(default_factory=list)


class RouteWhen(BaseModel):
    model_config = ConfigDict(extra="forbid")

    change_class: ChangeClass


class RouteRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(min_length=1)
    when: RouteWhen
    providers: list[RoutedProvider] = Field(min_length=1)


class EvidenceRoute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["evidence_route.v1"] = "evidence_route.v1"
    route_id: str = Field(min_length=1)
    tenant_id: str | None = None
    org_id: str | None = None
    repository: str | None = None
    task_id: str | None = None
    patch_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    llm_router: Literal[False] = False
    fail_closed: Literal[True] = True
    rules: list[RouteRule] = Field(min_length=1)
    notes: str | None = None


class BindingValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    all_candidate_items_bound: bool
    unbound_evidence_ids: list[str] = Field(default_factory=list)
    stale_evidence_ids: list[str] = Field(default_factory=list)
    mismatch_evidence_ids: list[str] = Field(default_factory=list)


class EvidenceCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required_classes: list[str] = Field(default_factory=list)
    present_classes: list[str] = Field(default_factory=list)
    missing_classes: list[str] = Field(default_factory=list)
    missing_treated_as_pass: Literal[False] = False


class EvidenceProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verification_passed: bool | None = None
    verification_incomplete: bool | None = None
    unit_receipts: list[Literal["TASK_NAMED", "FAILURE_DIRECT", "LOCAL_CREATION"]] = Field(
        default_factory=list
    )
    notes: str | None = None


class EvidenceConflict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conflict_id: str = Field(min_length=1)
    code: Literal["EVIDENCE_CONFLICT"] = "EVIDENCE_CONFLICT"
    evidence_ids: list[str] = Field(min_length=2)
    resolution: Literal["UNRESOLVED", "FAIL_CLOSED", "ESCALATE_DEFAULT"]
    notes: str | None = None


class VerificationEvidenceBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["verification_evidence_bundle.v1"] = "verification_evidence_bundle.v1"
    bundle_id: str = Field(min_length=1)
    repository: str = Field(min_length=1)
    source_sha: str = Field(min_length=7)
    patch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_id: str = Field(min_length=1)
    produced_at: str = Field(min_length=1)
    proposal_id: str | None = None
    task_id: str | None = None
    arm: str | None = None
    items: list[dict[str, Any]] = Field(default_factory=list)
    conflicts: list[EvidenceConflict] = Field(default_factory=list)
    binding_validation: BindingValidation
    coverage: EvidenceCoverage
    projection: EvidenceProjection
    incomplete_reasons: list[IncompleteReason] = Field(default_factory=list)
    notes: str | None = None
    bundle_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    required_provider_failures: list[str] = Field(default_factory=list)
    auto_admit_blocked: bool = False
