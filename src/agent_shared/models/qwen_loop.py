"""Bounded recursive Qwen loop result (T08 / impl order item 9)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "qwen_loop_result.v1"

LoopAction = Literal["retry", "stop"]

StopReason = Literal[
    "verification_passed",
    "sufficient_evidence",
    "budget_exhausted",
    "policy_denied",
    "human_required",
    "insufficient_evidence",
    "contradictory_evidence",
    "sandbox_failed",
    "disabled",
    "not_ci_failing",
]


class QwenLoopBudget(BaseModel):
    """Hard caps — the loop must never run without a finite bound."""

    max_plan_iterations: int = 2
    max_patch_iterations: int = 3
    max_ci_repair_iterations: int = 3
    max_selected_evidence_refs: int = 24
    max_selected_chars: int = 12000
    max_rejected_hypotheses: int = 10
    max_likely_files: int = 12


class SelectedEvidenceContext(BaseModel):
    """Evidence-selected context packet for the next Qwen attempt."""

    evidence_refs: list[str] = Field(default_factory=list)
    failure_class: str | None = None
    failure_fingerprints: list[str] = Field(default_factory=list)
    likely_files: list[str] = Field(default_factory=list)
    rejected_hypotheses: list[str] = Field(default_factory=list)
    recursive_context_digest: str | None = None
    summary: str = ""
    selection_sources: list[str] = Field(default_factory=list)


class QwenLoopAttemptRecord(BaseModel):
    attempt: int
    ci_verdict: str
    action: LoopAction
    stop_reason: StopReason | None = None
    evidence_ref_count: int = 0


class QwenLoopResult(BaseModel):
    schema_version: str = SCHEMA_VERSION
    schema_name: str = SCHEMA_VERSION
    session_id: str = ""
    run_id: str = ""
    repo: str = ""
    enabled: bool = True
    attempt: int = 0
    max_attempts: int = 3
    ci_verdict: str = ""
    action: LoopAction = "stop"
    stop_reason: StopReason = "disabled"
    selected_context: SelectedEvidenceContext = Field(default_factory=SelectedEvidenceContext)
    prior_attempts: list[QwenLoopAttemptRecord] = Field(default_factory=list)
    bounded: bool = True
    unbounded_forbidden: bool = True
    artifact_digest: str = ""
    created_at: str = ""
    updated_at: str = ""
    notes: list[str] = Field(default_factory=list)
