"""Context pack model."""

from __future__ import annotations

from pydantic import BaseModel, Field

from agent_shared.models.review import BlastRadiusContext


class ContextPack(BaseModel):
    schema_version: str = "context_pack.v1"
    project: str
    issue_number: int | None = None
    pr_number: int | None = None
    # Frozen at dispatch (Slice 5.5a identity invariant); optional for older packs.
    source_sha: str | None = None
    policy_source_sha: str | None = None
    issue_text: str | None = None
    diff_text: str | None = None
    adr_slice: list[dict] = Field(default_factory=list)
    blast_radius: BlastRadiusContext = Field(default_factory=BlastRadiusContext)
    search_hits: list[str] = Field(default_factory=list)
    prior_memory: list[dict] = Field(default_factory=list)
    context_sources: list[str] = Field(default_factory=list)
    provenance_items: list[dict[str, str]] = Field(default_factory=list)
    injection_assessments: list[dict] = Field(default_factory=list)
    budget: dict[str, int] = Field(default_factory=dict)
