"""Bounded failure evidence contract (VExp W2-0).

Distinct from ``agent_control.ci.failure_evidence`` (CI 6F.1). Model-visible
content is exposed only via ``to_prompt_projection()``; raw logs stay in refs.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_shared.hash_utils import canonical_json_hash

SCHEMA_VERSION = "failure_evidence.v1"

FAILURE_CLASS = Literal[
    "assertion_failure",
    "test_failure",
    "exception",
    "syntax_error",
    "timeout",
    "unknown",
]

MAX_ASSERTION_SUMMARY = 2000
MAX_EXCEPTION_SUMMARY = 2000
MAX_TRACEBACK_FRAMES = 20
MAX_FILE_PATHS = 32
MAX_SYMBOL_NAMES = 32


class TruncationMeta(BaseModel):
    """Audit-only truncation metadata."""

    model_config = ConfigDict(extra="forbid")

    assertion_summary_truncated: bool = False
    exception_summary_truncated: bool = False
    traceback_frames_truncated: bool = False
    file_paths_truncated: bool = False
    symbol_names_truncated: bool = False


class FailureEvidence(BaseModel):
    """Normalized, bounded verifier failure for repair input."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["failure_evidence.v1"] = SCHEMA_VERSION
    failure_id: str
    task_id: str
    session_id: str
    attempt_number: int = Field(ge=0)
    verifier_id: str
    verifier_scope: Literal["fast"] = "fast"
    command_id: str
    command: str
    display_name: str
    exit_code: int | None = None
    failure_class: FAILURE_CLASS
    failing_test_paths: list[str] = Field(default_factory=list)
    failing_test_ids: list[str] = Field(default_factory=list)
    assertion_summary: str = ""
    exception_summary: str = ""
    traceback_locations: list[str] = Field(default_factory=list)
    file_paths: list[str] = Field(default_factory=list)
    symbol_names: list[str] = Field(default_factory=list)
    patch_hash: str | None = None
    stdout_artifact_ref: str | None = None
    stderr_artifact_ref: str | None = None
    verification_artifact_ref: str | None = None
    normalizer_version: str = "failure_evidence_normalizer.v1"
    truncation: TruncationMeta = Field(default_factory=TruncationMeta)
    evidence_hash: str = ""

    @model_validator(mode="after")
    def _compute_hash(self) -> FailureEvidence:
        if not self.evidence_hash:
            body = self.model_dump(mode="json")
            body.pop("evidence_hash", None)
            object.__setattr__(self, "evidence_hash", canonical_json_hash(body))
        return self

    def to_schema_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def to_prompt_projection(self) -> dict[str, Any]:
        """Model-visible bounded projection; excludes raw log refs."""
        return {
            "failure_class": self.failure_class,
            "failing_test_paths": list(self.failing_test_paths),
            "failing_test_ids": list(self.failing_test_ids),
            "assertion_summary": self.assertion_summary,
            "exception_summary": self.exception_summary,
            "traceback_locations": list(self.traceback_locations),
            "file_paths": list(self.file_paths),
            "symbol_names": list(self.symbol_names),
            "command_id": self.command_id,
            "display_name": self.display_name,
            "attempt_number": self.attempt_number,
        }
