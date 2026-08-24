"""Authoritative verification handoff contract (VExp W2-0)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_shared.hash_utils import canonical_json_hash

SCHEMA_VERSION = "authoritative_handoff.v1"

RepairArm = Literal["control", "treatment"]


class AuthoritativeHandoff(BaseModel):
    """Frozen provenance bundle passed to authoritative dual verification."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["authoritative_handoff.v1"] = SCHEMA_VERSION
    task_id: str
    session_id: str
    invocation_id: str
    snapshot_sha: str
    repo_snapshot_id: str = ""
    context_pack_hash: str
    edit_policy_hash: str
    arm: RepairArm
    repair_action: str
    patch0_hash: str
    patch0_authorized: bool = True
    fast_verify0_hash: str
    repair_eligible: bool
    repair_gate_reason: str
    failure_evidence_hash: str | None = None
    repair_request_hash: str | None = None
    patch1_hash: str | None = None
    patch1_authorized: bool | None = None
    fast_verify1_hash: str | None = None
    final_candidate: Literal["patch0", "patch1"] = "patch0"
    repair_attempts: int = Field(default=0, ge=0)
    verifier_selection_hash: str = ""
    handoff_hash: str = ""

    @model_validator(mode="after")
    def _compute_hash(self) -> AuthoritativeHandoff:
        if not self.handoff_hash:
            body = self.model_dump(mode="json")
            body.pop("handoff_hash", None)
            object.__setattr__(self, "handoff_hash", canonical_json_hash(body))
        return self

    def to_schema_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
