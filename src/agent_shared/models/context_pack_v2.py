"""ContextPackV2 schema (VExp W0-B). Additive; v1 ContextPack remains the solver contract.

``prior_memory`` is never an authorization decision. The V1 adapter copies it to
``experience.compatibility.legacy_prior_memory`` and leaves ``authorized_records``
empty.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from agent_shared.models.repo_snapshot import RepoSnapshot

SCHEMA_VERSION = "context-pack.v2"
LEXICAL_SOURCE_V1_SEARCH_HITS = "context_pack.v1.search_hits"


class EvidenceItem(BaseModel):
    """One current-evidence or recursive-evidence item."""

    model_config = ConfigDict(extra="forbid")

    text: str
    source: str
    provenance: list[str] = Field(default_factory=list)


class CurrentEvidence(BaseModel):
    """Repository-current evidence, grouped by class. V1 compat fills lexical only."""

    model_config = ConfigDict(extra="forbid")

    lexical: list[EvidenceItem] = Field(default_factory=list)
    symbols: list[EvidenceItem] = Field(default_factory=list)
    dependency_edges: list[EvidenceItem] = Field(default_factory=list)
    tests: list[EvidenceItem] = Field(default_factory=list)
    config: list[EvidenceItem] = Field(default_factory=list)
    architecture: list[EvidenceItem] = Field(default_factory=list)


class ContextTask(BaseModel):
    """Task identity carried on a V2 pack. Solver-visible issue text lives here."""

    model_config = ConfigDict(extra="forbid")

    project: str = ""
    issue_number: int | None = None
    pr_number: int | None = None
    issue_text: str | None = None
    source_sha: str | None = None
    policy_source_sha: str | None = None


class ExperienceCompatibility(BaseModel):
    """Ungated v1 memory. Not an authorization verdict. Omit from render_v2."""

    model_config = ConfigDict(extra="forbid")

    legacy_prior_memory: list[dict[str, Any]] = Field(default_factory=list)


class ExperienceSection(BaseModel):
    """Historical experience. ``authorized_records`` is empty until a real gate exists."""

    model_config = ConfigDict(extra="forbid")

    candidates_considered: list[dict[str, Any]] = Field(default_factory=list)
    authorized_records: list[dict[str, Any]] = Field(default_factory=list)
    rejected_records: list[dict[str, Any]] = Field(default_factory=list)
    compatibility: ExperienceCompatibility = Field(default_factory=ExperienceCompatibility)


class ContextPackV2(BaseModel):
    """Versioned context schema that separates current evidence from experience."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["context-pack.v2"] = SCHEMA_VERSION
    task: ContextTask = Field(default_factory=ContextTask)
    repo_snapshot: RepoSnapshot | None = None
    current_evidence: CurrentEvidence = Field(default_factory=CurrentEvidence)
    experience: ExperienceSection = Field(default_factory=ExperienceSection)
    recursive_evidence: list[EvidenceItem] = Field(default_factory=list)
    budget: dict[str, int] = Field(default_factory=dict)
    provenance: list[dict[str, str]] = Field(default_factory=list)
    # Adapter reconstruction payload for render_v1_compatible. Not model-visible in render_v2.
    v1_compat: dict[str, Any] | None = None
