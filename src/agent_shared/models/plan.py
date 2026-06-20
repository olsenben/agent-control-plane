"""Structured plan output models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from agent_shared.models.review import BlastRadiusContext


class PlanStep(BaseModel):
    id: str
    summary: str
    files: list[str] = Field(default_factory=list)


class PlanResult(BaseModel):
    schema_version: str = "plan_result.v1"
    scope_summary: str = ""
    steps: list[PlanStep] = Field(default_factory=list)
    ci_hints: list[str] = Field(default_factory=list)
    blast_radius: BlastRadiusContext = Field(default_factory=BlastRadiusContext)
    assumptions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    confidence: str = "medium"
    recommended_next_command: str = "/agent fix"
    risk_tags: list[str] = Field(default_factory=list)
