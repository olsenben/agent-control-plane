"""Trajectory memory models (memory_record.v1)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from agent_shared.models.plan import PlanResult
from agent_shared.models.review import BlastRadiusContext, ReviewFinding, ReviewResult

MemoryQuality = Literal["model_generated", "structured_result", "human_verified"]
PromptHashSource = Literal["final_prompt", "not_available"]
RiskTagSourceKind = Literal["model_output", "policy_gate", "semgrep", "human"]
SourceCommand = Literal["inspect", "explain", "review", "plan", "fix"]
PolicyDecision = Literal["allow", "deny", "pending_approval"]
Staleness = Literal["fresh", "aging", "stale"]


class RiskTagSource(BaseModel):
    tag: str
    source: RiskTagSourceKind


class MemoryGovernance(BaseModel):
    risk_tags: list[str] = Field(default_factory=list)
    risk_tag_sources: list[RiskTagSource] = Field(default_factory=list)
    policy_decision: PolicyDecision = "allow"
    risk_class: int = 1


class MemoryAudit(BaseModel):
    prompt_hash: str | None = None
    prompt_hash_source: PromptHashSource = "not_available"
    summary_hash: str | None = None
    context_sources: list[str] = Field(default_factory=list)
    model_tier: str | None = None
    engine: str = ""
    ingested_at: str = ""


class RecommendedNextStep(BaseModel):
    command: str
    rationale: str = ""
    machine_readable: dict[str, Any] = Field(default_factory=dict)


class MemoryRecord(BaseModel):
    schema_version: str = "memory_record.v1"
    record_id: str
    run_id: str

    repo_owner: str
    repo_name: str
    repo_full_name: str
    issue_id: int | None = None
    pr_id: int | None = None
    branch: str = "main"
    commit_sha: str | None = None

    source_command: SourceCommand
    source_run_id: str
    source_model: str | None = None
    source_engine: str | None = None
    source_commit_sha: str | None = None
    confidence: str = "medium"
    memory_quality: MemoryQuality = "model_generated"

    created_at: str
    updated_at: str
    is_stale: bool = False
    staleness_reason: str | None = None
    staleness: Staleness = "fresh"

    files_inspected: list[str] = Field(default_factory=list)
    files_touched: list[str] = Field(default_factory=list)
    adr_ids_applied: list[str] = Field(default_factory=list)
    blast_radius: BlastRadiusContext = Field(default_factory=BlastRadiusContext)
    findings: list[ReviewFinding] = Field(default_factory=list)

    failing_tests: list[str] = Field(default_factory=list)
    suspected_root_cause: str | None = None
    rejected_hypotheses: list[str] = Field(default_factory=list)
    uncertain_hypotheses: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    uncertainty_notes: str | None = None

    governance: MemoryGovernance = Field(default_factory=MemoryGovernance)
    recommended_next_step: RecommendedNextStep | None = None
    audit: MemoryAudit = Field(default_factory=MemoryAudit)

    # Retained for mapper convenience; not duplicated in selective FTS text.
    review_result: ReviewResult | None = None
    plan_result: PlanResult | None = None
