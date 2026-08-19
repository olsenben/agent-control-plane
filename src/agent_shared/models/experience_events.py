"""Verified-experience telemetry vocabulary and common envelope (VExp W0-D).

Freezes the 17 ``domain.action`` event names, the common envelope, and the
``TreatmentExposure`` blob from epic §4.4. Per-event W3–W7 payload schemas are
not defined here; owning waves version those payloads when they exist.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

EXPERIENCE_EVENT_NAMES: tuple[str, ...] = (
    "context.candidate_evidence",
    "context.evidence_selected",
    "memory.candidate_retrieved",
    "memory.applicability_checked",
    "memory.exposure_authorized",
    "memory.exposure_abstained",
    "memory.behavioral_use_observed",
    "patch.generated",
    "verification.fast.completed",
    "repair.requested",
    "repair.completed",
    "verification.authoritative.completed",
    "experience.admission_decided",
    "memory.utility_labeled",
    "memory.validity_changed",
    "recursion.requested",
    "recursion.completed",
)

EXPERIENCE_EVENT_NAME_SET: frozenset[str] = frozenset(EXPERIENCE_EVENT_NAMES)

ExperienceEventName = Literal[
    "context.candidate_evidence",
    "context.evidence_selected",
    "memory.candidate_retrieved",
    "memory.applicability_checked",
    "memory.exposure_authorized",
    "memory.exposure_abstained",
    "memory.behavioral_use_observed",
    "patch.generated",
    "verification.fast.completed",
    "repair.requested",
    "repair.completed",
    "verification.authoritative.completed",
    "experience.admission_decided",
    "memory.utility_labeled",
    "memory.validity_changed",
    "recursion.requested",
    "recursion.completed",
]


class TreatmentExposure(BaseModel):
    """Treatment-realization fields from epic §4.4. No prompt or secret bodies."""

    model_config = ConfigDict(extra="forbid")

    repo_snapshot_id: str | None = None
    context_pack_version: str | None = None
    evidence_provider_ids: list[str] = Field(default_factory=list)
    candidate_memory_ids: list[str] = Field(default_factory=list)
    applicability_verdicts: list[str] = Field(default_factory=list)
    exposed_memory_ids: list[str] = Field(default_factory=list)
    recursive_invocations: int = 0
    repair_attempt_index: int = 0
    official_verification_result: bool | None = None
    additional_verification_result: bool | None = None


class ExperienceEventEnvelope(BaseModel):
    """Common telemetry envelope. Payloads stay untyped beyond this wave."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["experience_event.v1"] = "experience_event.v1"
    event_name: str
    event_id: str | None = None
    recorded_at: str | None = None
    correlation_id: str | None = None
    trace_id: str | None = None
    session_id: str | None = None
    run_id: str | None = None
    treatment: TreatmentExposure | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_name")
    @classmethod
    def _registered_name(cls, value: str) -> str:
        if value not in EXPERIENCE_EVENT_NAME_SET:
            raise ValueError(f"unregistered experience event name: {value}")
        return value
