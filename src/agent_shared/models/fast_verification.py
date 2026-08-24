"""Fast verification contracts (VExp W2-0).

Fast verification is advisory only; ``can_finalize_episode`` is always false.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_shared.hash_utils import canonical_json_hash
from agent_shared.models.experience_verification import (
    ExperienceVerificationResult,
    VerificationLane,
)

VERIFIER_SELECTION_VERSION = "verifier_selection.v1"
REQUEST_VERSION = "fast_verification_request.v1"
RESULT_VERSION = "fast_verification_result.v1"

VerifierSource = Literal["eval_manifest", "registry"]
FastVerifyStatus = Literal[
    "passed",
    "failed",
    "error",
    "timeout",
    "unavailable",
    "blocked",
    "infrastructure",
]
FailureOrigin = Literal["evaluated_agent", "infrastructure", "harness", "none"]


class VerifierSelection(BaseModel):
    """Deterministic fast-verifier binding chosen by control plane."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["verifier_selection.v1"] = VERIFIER_SELECTION_VERSION
    verifier_id: str
    source: VerifierSource
    command_ref: str
    display_name: str
    timeout_s: int = Field(default=120, ge=1)
    output_limit_bytes: int = Field(default=1_048_576, ge=1)
    scope: Literal["fast"] = "fast"
    provenance_hash: str = ""

    @model_validator(mode="after")
    def _compute_provenance(self) -> VerifierSelection:
        if not self.provenance_hash:
            body = {
                "verifier_id": self.verifier_id,
                "source": self.source,
                "command_ref": self.command_ref,
                "display_name": self.display_name,
                "timeout_s": self.timeout_s,
                "output_limit_bytes": self.output_limit_bytes,
                "scope": self.scope,
            }
            object.__setattr__(self, "provenance_hash", canonical_json_hash(body))
        return self

    def to_schema_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class FastVerificationRequest(BaseModel):
    """Request to run one bounded fast verification attempt."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["fast_verification_request.v1"] = REQUEST_VERSION
    task_id: str
    session_id: str
    snapshot_sha: str
    patch_hash: str
    verifier_selection: VerifierSelection
    attempt_number: int = Field(ge=0)


class FastVerificationResult(BaseModel):
    """Advisory fast verification outcome; never final authority."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["fast_verification_result.v1"] = RESULT_VERSION
    task_id: str
    session_id: str
    snapshot_sha: str
    patch_hash: str
    attempt_number: int = Field(ge=0)
    status: FastVerifyStatus
    failure_origin: FailureOrigin
    can_finalize_episode: Literal[False] = False
    verifier_selection: VerifierSelection
    exit_code: int | None = None
    duration_seconds: float | None = None
    stdout_artifact_ref: str | None = None
    stderr_artifact_ref: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    result_hash: str = ""

    @model_validator(mode="after")
    def _compute_hash(self) -> FastVerificationResult:
        if not self.result_hash:
            body = self.model_dump(mode="json")
            body.pop("result_hash", None)
            object.__setattr__(self, "result_hash", canonical_json_hash(body))
        return self

    @property
    def is_advisory_only(self) -> bool:
        return not self.can_finalize_episode

    def to_schema_dict(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        return payload

    def to_experience_verification(self) -> ExperienceVerificationResult:
        """Map to shared ExperienceVerificationResult (fast advisory lane)."""
        passed = self.status == "passed"
        return ExperienceVerificationResult(
            verification_scope="fast",
            authority_domain="ct104_advisory",
            official=VerificationLane(
                commands=[self.verifier_selection.command_ref],
                passed=passed,
            ),
            additional=VerificationLane(commands=[], passed=False),
            verified_success=passed,
            failure_class=self.status if not passed else None,
            evidence_refs=[
                ref
                for ref in (
                    self.stdout_artifact_ref,
                    self.stderr_artifact_ref,
                )
                if ref
            ],
            started_at=self.started_at,
            finished_at=self.finished_at,
        )


def fast_result_hash(result: FastVerificationResult) -> str:
    return result.result_hash or canonical_json_hash(
        {k: v for k, v in result.model_dump(mode="json").items() if k != "result_hash"}
    )
