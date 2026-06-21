"""Structured parse failure artifact model."""

from __future__ import annotations

from pydantic import BaseModel, Field

from agent_shared.models.review import BlastRadiusContext


class RecommendedNextStep(BaseModel):
    command: str = "retry"
    reason: str = "model returned invalid structured output"


class ParseFailureArtifact(BaseModel):
    schema_version: str = "parse_failure.v1"
    run_id: str
    command_kind: str
    status: str = "failed_structured_parse"
    parse_errors: list[str] = Field(default_factory=list)
    raw_response_excerpt: str = ""
    context_sources: list[str] = Field(default_factory=list)
    blast_radius: BlastRadiusContext = Field(default_factory=BlastRadiusContext)
    prior_memory_used: list[dict] = Field(default_factory=list)
    recommended_next_step: RecommendedNextStep = Field(default_factory=RecommendedNextStep)
