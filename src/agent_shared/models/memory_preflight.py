"""Deterministic context preflight + thin context packet (Slice 5.5a / 8b)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ComponentStatus = Literal["complete", "unavailable", "truncated"]
PreflightStatus = Literal["complete", "degraded"]

COMPILER_VERSION = "memory_preflight.v1/8b"

# Hard collection bounds (stable truncation).
MAX_RELEVANT_PRIOR_RUNS = 10
MAX_KNOWN_REPO_CONVENTIONS = 20
MAX_LIKELY_FILES = 50
MAX_KNOWN_FAILURE_MODES = 10
MAX_REJECTED_HYPOTHESES = 10
MAX_EVIDENCE_EVENT_IDS = 100
MAX_CI_EVIDENCE_POINTERS = 20
MAX_CITATIONS = 100
MAX_GRAPH_QUERIES = 5
MAX_MISSING_GRAPH_EDGES = 50
MAX_STRING_LEN = 512
MAX_EVENTS_SCANNED = 1000

# Heuristic thresholds (count-based; no pack-budget circularity).
THRESHOLD_PRIOR_MEMORY = 8
THRESHOLD_DISTINCT_ROOT_CAUSES = 2
THRESHOLD_MISSING_GRAPH_EDGES = 10


class ComponentResults(BaseModel):
    prior_memory: ComponentStatus = "complete"
    graph: ComponentStatus = "complete"
    adr: ComponentStatus = "complete"
    events: ComponentStatus = "complete"
    ci_evidence: ComponentStatus = "complete"


class HeuristicInputs(BaseModel):
    prior_memory_count: int = 0
    distinct_prior_root_causes: int = 0
    missing_graph_edge_count: int = 0


class SessionArtifactRef(BaseModel):
    """Durable reference stored on AgentSession after atomic persist."""

    artifact_type: Literal["memory_preflight", "context_packet", "verification_claim"]
    relative_path: str
    digest: str
    byte_size: int
    schema_name: str
    created_at: str


class MemoryPreflight(BaseModel):
    schema_version: str = "memory_preflight.v1"
    session_id: str
    run_id: str
    repo: str
    issue_id: int | None = None
    pr_number: int | None = None
    source_sha: str
    policy_source_sha: str = ""
    created_at: str
    compiler_version: str = COMPILER_VERSION
    status: PreflightStatus = "complete"
    artifact_digest: str = ""
    retrieval_mode: Literal["deterministic_only"] = "deterministic_only"
    recursive_context_required: bool = False
    invocation_reasons: list[str] = Field(default_factory=list)
    skip_reason: str | None = None
    decision_summary: str | None = None
    heuristic_inputs: HeuristicInputs = Field(default_factory=HeuristicInputs)
    component_results: ComponentResults = Field(default_factory=ComponentResults)
    component_errors: dict[str, str] = Field(default_factory=dict)
    truncated_sections: list[str] = Field(default_factory=list)
    relevant_prior_runs: list[dict] = Field(default_factory=list)
    known_repo_conventions: list[dict] = Field(default_factory=list)
    likely_files: list[str] = Field(default_factory=list)
    known_failure_modes: list[str] = Field(default_factory=list)
    rejected_hypotheses_from_prior_runs: list[str] = Field(default_factory=list)
    graph_queries: list[dict] = Field(default_factory=list)
    # Blast counts plus Orbit coverage (edge_kinds, provenance_counts, …).
    graph_coverage: dict[str, Any] = Field(default_factory=dict)
    missing_graph_edges: list[str] = Field(default_factory=list)
    evidence_event_ids: list[str] = Field(default_factory=list)
    ci_evidence_pointers: list[dict] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)
    staleness: list[str] = Field(default_factory=list)
    recommended_verification: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)


class ContextPacket(BaseModel):
    """Thin handoff manifest — digests/refs only; worker still uses context_pack."""

    schema_version: str = "context_packet.v1"
    session_id: str
    run_id: str
    repo: str
    source_sha: str
    policy_source_sha: str = ""
    created_at: str
    preflight_digest: str
    preflight_relative_path: str
    context_pack_digest: str
    bounded_source_index: list[str] = Field(default_factory=list)
    truncation_budget: dict[str, int] = Field(default_factory=dict)
    artifact_digest: str = ""
