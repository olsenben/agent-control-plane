"""Injection assessment schema (V6 T06) — shadow mode only."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

InjectionRisk = Literal["none", "low", "medium", "high"]
RecommendedAction = Literal["allow", "flag", "exclude", "block"]


class MatchedRegion(BaseModel):
    start: int
    end: int
    snippet: str = ""
    category: str = ""


class InjectionAssessment(BaseModel):
    schema_version: str = "injection_assessment.v1"
    mode: Literal["shadow"] = "shadow"
    risk: InjectionRisk = "none"
    categories: list[str] = Field(default_factory=list)
    matched_regions: list[MatchedRegion] = Field(default_factory=list)
    recommended_action: RecommendedAction = "allow"
    scanner: str = "modular_shadow"
    authority_granted: bool = False
    """Always False — scanner never grants authority (provenance/policy only)."""
    content_ref: str = ""
    detail: dict[str, Any] = Field(default_factory=dict)
    assessed_at: str = ""
    run_id: str | None = None
    session_id: str | None = None
    project: str = ""
