"""Closed-world diff gate result models (Slice 6C)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ViolationCode = Literal[
    "diff_size_exceeded",
    "always_denied_path",
    "elevated_approval_required",
    "out_of_scope_path",
    "lockfile_edit",
    "generated_state_edit",
    "secret_exposure",
    "test_weakening_detected",
    "blast_radius_hash_mismatch",
    "blast_radius_test_drift",
    "ci_hints_drift",
    "blast_radius_adr_drift",
]

WarningCode = Literal["plan_scope_drift", "graph_incomplete"]


class DiffGateViolation(BaseModel):
    code: str
    path: str | None = None
    message: str = ""


class DiffGateWarning(BaseModel):
    code: str
    paths: list[str] = Field(default_factory=list)
    message: str = ""


class CiMatrixSelection(BaseModel):
    narrow_tests: list[str] = Field(default_factory=list)
    workflows: list[str] = Field(default_factory=list)
    raw_hints: list[str] = Field(default_factory=list)
    selection_source: list[str] = Field(default_factory=list)
    dispatch: str = "deferred_6e"


class DiffGateResult(BaseModel):
    schema_version: str = "diff_gate_result.v1"
    passed: bool = False
    policy_version: str = "closed_world_policy.v1"
    policy_sources: list[str] = Field(default_factory=list)
    approval_id: str | None = None
    approval_target_id: str | None = None
    plan_run_id: str | None = None
    blast_radius_hash: str | None = None
    recomputed_blast_radius_hash: str | None = None
    allowed_files: list[str] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    violations: list[DiffGateViolation] = Field(default_factory=list)
    warnings: list[DiffGateWarning] = Field(default_factory=list)
    selected_ci_matrix: CiMatrixSelection = Field(default_factory=CiMatrixSelection)

    def violation_codes(self) -> list[str]:
        return [v.code for v in self.violations]

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "diff_gate_passed": self.passed,
            "diff_gate_violation_codes": self.violation_codes(),
            "policy_sources": list(self.policy_sources),
        }
