"""durable_patch_capability.v1 production envelope."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_shared.models.transaction.identity import IdentityPrincipal

ISSUER = "authoritative_control_plane"

CapabilityLifecycle = Literal[
    "MINTED",
    "CONSUMING",
    "CONSUMED",
    "EXPIRED",
    "INVALIDATED",
]


class DurablePatchCapability(BaseModel):
    """One-shot exact-patch capability. Secret material is store-only."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["durable_patch_capability.v1"] = "durable_patch_capability.v1"
    capability_id: str = Field(min_length=1)
    issuer: Literal["authoritative_control_plane"] = ISSUER
    repo: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    org_id: str = Field(min_length=1)
    source_sha: str = Field(min_length=7)
    patch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    allowed_target_branch: str = Field(min_length=1)
    policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    verification_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    admission_decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_bundle_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    task_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    human_initiator: IdentityPrincipal
    agent_identity: IdentityPrincipal
    issued_at: str = Field(min_length=1)
    expires_at: str | None = None
    one_shot: Literal[True] = True
    expires_conceptually: Literal[True] = True
    does_not_authorize_subsequent_edits: Literal[True] = True
    consumed: bool = False
    lifecycle: CapabilityLifecycle = "MINTED"
    issuer_identity: str = ISSUER
    capability_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def derive_consumed_from_lifecycle(self) -> DurablePatchCapability:
        lifecycle = self.lifecycle
        if self.consumed and lifecycle == "MINTED":
            lifecycle = "CONSUMED"
            object.__setattr__(self, "lifecycle", lifecycle)
        object.__setattr__(self, "consumed", lifecycle == "CONSUMED")
        return self


class CapabilityPublicReceipt(BaseModel):
    """Non-secret capability metadata safe for Observatory / worker APIs."""

    model_config = ConfigDict(extra="forbid")

    capability_id: str
    repo: str
    source_sha: str
    patch_digest: str
    allowed_target_branch: str
    issued_at: str
    expires_at: str | None = None
    consumed: bool
    lifecycle: CapabilityLifecycle = "MINTED"
    expired: bool = False
    replayed: bool = False
    issuer: str = ISSUER
