"""transaction_preflight.v1 and policy_bundle_receipt.v1 envelopes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PreflightStatus = Literal["READY", "INCOMPLETE"]
IncompleteReason = Literal["PDP_INPUT_INCOMPLETE", "POLICY_UNAVAILABLE"]
G0InputState = Literal[
    "G0_PRESENT_NONEMPTY",
    "G0_PRESENT_EXPLICIT_EMPTY",
    "G0_LOAD_FAILED",
    "G0_UNBOUND",
    "G0_SCHEMA_INVALID",
]


class TransactionPreflight(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["transaction_preflight.v1"] = "transaction_preflight.v1"
    status: PreflightStatus
    missing_inputs: list[str] = Field(default_factory=list)
    incomplete_reason: IncompleteReason | None = None
    g0_input_state: G0InputState | None = None
    policy_bundle_digest: str | None = None
    deterministic_preflight_revisit: Literal["YES"] = "YES"


class PolicyBundleReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["policy_bundle_receipt.v1"] = "policy_bundle_receipt.v1"
    bundle_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    frozen_c_hash: str | None = None
    expected_frozen_c_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    admission_implementation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    g0_input_state: G0InputState
    g0_source_identity: str | None = None
    c_load_mode: str | None = None
    ruleset_present: bool = False
    created_at: str | None = None
