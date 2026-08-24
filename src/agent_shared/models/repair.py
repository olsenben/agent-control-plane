"""Repair contracts and gate logic (VExp W2-0)."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_shared.hash_utils import canonical_json_hash
from agent_shared.models.failure_evidence import FailureEvidence
from agent_shared.models.fast_verification import FastVerificationResult

REPAIR_GATE_VERSION = "repair_gate.v1"
REPAIR_BUDGET_VERSION = "repair_budget.v1"
REPAIR_REQUEST_VERSION = "repair_request.v1"
REPAIR_CONTEXT_VERSION = "repair_context.v1"
REPAIR_OUTCOME_VERSION = "repair_outcome.v1"
REPAIR_ATTEMPT_VERSION = "repair_attempt_record.v1"

MAX_REPAIR_ATTEMPTS = 1
MAX_TOTAL_GENERATION_CALLS = 2
MAX_FAST_VERIFY_ATTEMPTS = 2
MAX_FAST_VERIFY_WALLCLOCK_S = 120
MAX_REPAIR_INPUT_CHARS = 24000
MAX_TOTAL_TASK_WALLCLOCK_S = 1800


class RepairControllerState(str, Enum):
    """Deterministic repair orchestration states."""

    TASK_READY = "task_ready"
    CONTEXT_FROZEN = "context_frozen"
    PATCH0_GENERATED = "patch0_generated"
    PATCH0_AUTHORIZED = "patch0_authorized"
    PATCH0_FROZEN = "patch0_frozen"
    FAST_VERIFY_0 = "fast_verify_0"
    REPAIR_GATE = "repair_gate"
    FORK = "fork"
    REPAIR_REQUEST_1 = "repair_request_1"
    PATCH1_GENERATED = "patch1_generated"
    PATCH1_AUTHORIZED = "patch1_authorized"
    FAST_VERIFY_1 = "fast_verify_1"
    CANDIDATE_PATCH1 = "candidate_patch1"
    KEEP_PATCH0 = "keep_patch0"
    CONTROL_AUTH = "control_auth"
    TREATMENT_AUTH_P0 = "treatment_auth_p0"
    TREATMENT_AUTH_P1 = "treatment_auth_p1"
    TERMINAL_POLICY = "terminal_policy"
    EXHAUSTED_NO_CANDIDATE = "exhausted_no_candidate"


RepairAction = Literal["disabled", "observe_fast_only", "one_repair"]
FinalCandidate = Literal["patch0", "patch1"]


class RepairGate(BaseModel):
    """Pure repair eligibility gate from frozen FastVerify0 observation."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["repair_gate.v1"] = REPAIR_GATE_VERSION
    repair_eligible: bool
    repair_gate_reason: str

    def to_schema_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class RepairBudget(BaseModel):
    """Frozen W2 budget constants."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["repair_budget.v1"] = REPAIR_BUDGET_VERSION
    max_repair_attempts: Literal[1] = MAX_REPAIR_ATTEMPTS
    max_total_generation_calls: Literal[2] = MAX_TOTAL_GENERATION_CALLS
    max_fast_verify_attempts: Literal[2] = MAX_FAST_VERIFY_ATTEMPTS
    max_fast_verify_wallclock_s: int = MAX_FAST_VERIFY_WALLCLOCK_S
    max_repair_input_chars: int = MAX_REPAIR_INPUT_CHARS
    max_total_task_wallclock_s: int = MAX_TOTAL_TASK_WALLCLOCK_S
    remaining_repair_attempts: int = Field(default=1, ge=0)

    @classmethod
    def default(cls) -> RepairBudget:
        return cls()


class RepairRequest(BaseModel):
    """Bounded repair model call request."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["repair_request.v1"] = REPAIR_REQUEST_VERSION
    task_id: str
    session_id: str
    patch0_hash: str
    evidence_hash: str
    context_pack_hash: str
    edit_policy_hash: str
    instruction_id: Literal["repair_instruction.v1"] = "repair_instruction.v1"
    attempt_number: int = Field(default=1, ge=1, le=1)
    request_hash: str = ""

    @model_validator(mode="after")
    def _compute_hash(self) -> RepairRequest:
        if not self.request_hash:
            body = self.model_dump(mode="json")
            body.pop("request_hash", None)
            object.__setattr__(self, "request_hash", canonical_json_hash(body))
        return self


class RepairContext(BaseModel):
    """Frozen inputs available to the repair model."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["repair_context.v1"] = REPAIR_CONTEXT_VERSION
    task_id: str
    session_id: str
    snapshot_sha: str
    patch0_hash: str
    context_pack_hash: str
    edit_policy_hash: str
    failure_evidence_hash: str
    instruction_id: Literal["repair_instruction.v1"] = "repair_instruction.v1"
    repair_instruction: str = (
        "The previous patch failed the bounded verifier. Repair the implementation "
        "using the provided failure evidence. Preserve valid changes. Respect "
        "edit_policy. Return one FixResult in the existing format."
    )


class RepairAttemptRecord(BaseModel):
    """Audit record for one repair attempt."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["repair_attempt_record.v1"] = REPAIR_ATTEMPT_VERSION
    attempt_number: int = Field(default=1, ge=1, le=1)
    repair_invoked: bool = False
    parse_success: bool | None = None
    authorized: bool | None = None
    applied: bool | None = None
    policy_rejected: bool = False
    fast_verify_status: str | None = None
    final_candidate: FinalCandidate = "patch0"
    patch1_hash: str | None = None


class RepairOutcome(BaseModel):
    """Result of repair orchestration for one arm."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["repair_outcome.v1"] = REPAIR_OUTCOME_VERSION
    repair_invoked: bool = False
    repair_completed: bool = False
    repair_attempts: int = Field(default=0, ge=0)
    final_candidate: FinalCandidate = "patch0"
    patch0_hash: str = ""
    patch1_hash: str | None = None
    attempt_record: RepairAttemptRecord = Field(default_factory=RepairAttemptRecord)
    repair_gate: RepairGate | None = None


def compute_repair_gate(
    *,
    fast_result: FastVerificationResult,
    failure_evidence: FailureEvidence | None,
    budget: RepairBudget | None = None,
    patch0_authorized: bool = True,
    patch0_applied: bool = True,
    repair_mode: RepairAction = "one_repair",
) -> RepairGate:
    """Deterministic repair eligibility from frozen FastVerify0 observation."""
    if repair_mode in {"disabled", "observe_fast_only"}:
        return RepairGate(repair_eligible=False, repair_gate_reason="repair_action_disabled")
    if not patch0_authorized:
        return RepairGate(repair_eligible=False, repair_gate_reason="patch0_not_authorized")
    if not patch0_applied:
        return RepairGate(repair_eligible=False, repair_gate_reason="patch0_not_applied")
    if fast_result.status == "passed":
        return RepairGate(repair_eligible=False, repair_gate_reason="fast_pass")
    if fast_result.status != "failed":
        return RepairGate(
            repair_eligible=False,
            repair_gate_reason=f"fast_status_{fast_result.status}",
        )
    if fast_result.failure_origin != "evaluated_agent":
        return RepairGate(
            repair_eligible=False,
            repair_gate_reason=f"failure_origin_{fast_result.failure_origin}",
        )
    if failure_evidence is None:
        return RepairGate(repair_eligible=False, repair_gate_reason="normalization_error")
    remaining = (budget or RepairBudget.default()).remaining_repair_attempts
    if remaining <= 0:
        return RepairGate(repair_eligible=False, repair_gate_reason="budget_exhausted")
    return RepairGate(repair_eligible=True, repair_gate_reason="eligible_failure")
