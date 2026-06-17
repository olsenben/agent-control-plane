"""Structured review output models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["info", "warn", "error"]


class ReviewFinding(BaseModel):
    id: str
    severity: Severity = "info"
    summary: str
    file: str | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    risk_tags: list[str] = Field(default_factory=list)


class BlastRadiusContext(BaseModel):
    affected_repos: list[str] = Field(default_factory=list)
    affected_services: list[str] = Field(default_factory=list)
    affected_tests: list[str] = Field(default_factory=list)
    related_adrs: list[str] = Field(default_factory=list)
    missing_graph_edges: list[str] = Field(default_factory=list)


class ReviewResult(BaseModel):
    schema_version: str = "review_result.v1"
    findings: list[ReviewFinding] = Field(default_factory=list)
    files_inspected: list[str] = Field(default_factory=list)
    blast_radius: BlastRadiusContext = Field(default_factory=BlastRadiusContext)
    confidence: str = "medium"
    recommended_next_command: str = "/agent plan"
    risk_tags: list[str] = Field(default_factory=list)


def stub_blast_radius() -> BlastRadiusContext:
    return BlastRadiusContext(missing_graph_edges=["not implemented"])
