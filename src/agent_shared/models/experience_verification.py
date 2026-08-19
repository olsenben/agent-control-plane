"""Cross-plane verification result contract (VExp W0-C).

``can_finalize_production_episode`` is derived from ``authority_domain`` and is
never an input field. Final-for-eval (``eval_harness`` + ``verification_scope``
``final``) does not authorize production episode finalization.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "experience_verification_result.v1"

VerificationScope = Literal["fast", "final"]
AuthorityDomain = Literal["ct104_advisory", "ct102_production", "eval_harness"]


class VerificationLane(BaseModel):
    """One independent command lane (official or additional)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    commands: list[str] = Field(default_factory=list)
    passed: bool = Field(alias="pass")


class ExperienceVerificationResult(BaseModel):
    """Machine-readable verification result shared by CT104, CT102, and eval."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: Literal["experience_verification_result.v1"] = SCHEMA_VERSION
    verification_scope: VerificationScope
    authority_domain: AuthorityDomain
    official: VerificationLane
    additional: VerificationLane
    verified_success: bool
    failure_class: str | None = None
    normalized_failures: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    started_at: str | None = None
    finished_at: str | None = None

    @property
    def can_finalize_production_episode(self) -> bool:
        """True only when the authority domain is production CT102."""
        return self.authority_domain == "ct102_production"

    def to_schema_dict(self) -> dict[str, Any]:
        """JSON-schema payload. Does not include derived properties."""
        return self.model_dump(mode="json", by_alias=True)
