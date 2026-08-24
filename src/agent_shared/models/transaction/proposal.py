"""patch_proposal.v1. Immutable after finalize."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_shared.models.transaction.identity import CompositeIdentity, IdentityPrincipal


class PatchProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["patch_proposal.v1"] = "patch_proposal.v1"
    session_id: str = Field(min_length=1)
    proposal_id: str | None = None
    repo: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    org_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    source_sha: str = Field(min_length=7)
    source_tree_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    patch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    changed_files: list[str] = Field(default_factory=list)
    changed_symbols: list[str] = Field(default_factory=list)
    created_units: list[str] = Field(default_factory=list)
    deleted_units: list[str] = Field(default_factory=list)
    actor_identity: IdentityPrincipal
    worker_identity: IdentityPrincipal
    identity: CompositeIdentity | None = None
    created_at: str = Field(min_length=1)
    finalized_at: str | None = None
    raw_patch_location: str = Field(min_length=1)
    raw_patch_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    finalized: bool = False
    immutable_after_finalize: Literal[True] = True
    notes: str | None = None

    @model_validator(mode="after")
    def _finalized_timestamp(self) -> PatchProposal:
        if self.finalized and not self.finalized_at:
            raise ValueError("finalized_at required when finalized is true")
        return self
