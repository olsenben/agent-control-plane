"""Recursive context result schema (Phase 20 / slice 8c)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "recursive_context_result.v1"

ControllerBackend = Literal["deterministic", "model"]

StopReason = Literal[
    "deterministic_preflight_sufficient",
    "sufficient_evidence",
    "contradictory_evidence",
    "policy_denied",
    "budget_exhausted",
    "human_required",
    "fallback_deterministic",
    "skipped",
]


class RecursiveContextBudget(BaseModel):
    max_depth: int = 2
    max_subcalls: int = 6
    max_graph_queries: int = 20
    max_memory_records: int = 24
    max_wall_seconds: int = 180
    max_prompt_tokens_per_subcall: int = 8192
    max_total_input_tokens: int = 60000
    max_total_output_tokens: int = 12000
    output_max_chars: int = 16000


class RecursiveContextBudgetUsed(BaseModel):
    depth: int = 0
    subcalls: int = 0
    graph_queries: int = 0
    memory_records: int = 0
    wall_seconds: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: int = 0


class RecursiveContextSubcall(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)
    summary: str = ""
    depth: int = 0


class RecursiveContextResult(BaseModel):
    schema_version: str = SCHEMA_VERSION
    # Alias for V4 plan field name "schema"
    schema_name: str = SCHEMA_VERSION
    session_id: str = ""
    run_id: str
    repo: str = ""
    question: str = ""
    recursive_context_required: bool = False
    invoked: bool = False
    skipped: bool = False
    invocation_reasons: list[str] = Field(default_factory=list)
    skip_reason: str | None = None
    graph_queries: list[dict[str, Any]] = Field(default_factory=list)
    memory_records_used: list[str] = Field(default_factory=list)
    subcalls: list[RecursiveContextSubcall] = Field(default_factory=list)
    supported_hypotheses: list[str] = Field(default_factory=list)
    rejected_hypotheses: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    remaining_uncertainty: list[str] = Field(default_factory=list)
    recommended_next_evidence: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    budget: RecursiveContextBudget = Field(default_factory=RecursiveContextBudget)
    budget_used: RecursiveContextBudgetUsed = Field(default_factory=RecursiveContextBudgetUsed)
    stop_reason: StopReason = "skipped"
    controller_mode: Literal["skipped", "deterministic", "model_2070", "fallback_deterministic"] = (
        "skipped"
    )
    # V10 T00.5 — C0/C1 controller telemetry. Additive with defaults so existing
    # recursive_context_result.v1 artifacts stay loadable.
    controller_backend: ControllerBackend = "deterministic"
    controller_model_invoked: bool = False
    controller_role: str = ""
    controller_role_label: str = ""
    controller_model_id: str = ""
    # endpoint_reported | configured | planned_not_invoked — a C1 proof needs the
    # first, because the other two only echo local configuration back.
    controller_model_id_source: str = ""
    controller_provider: str = ""
    controller_attempts: int = 0
    controller_prompt_tokens: int = 0
    controller_completion_tokens: int = 0
    controller_wall_seconds: float = 0.0
    # None means the endpoint did not report the timing; it is never a measured
    # zero. Absent metrics are named in `controller_missing_fields`.
    controller_gpu_seconds: float | None = None
    controller_data_left_homelab: bool = False
    controller_error_class: str = ""
    # V10 Wave C — local-only trust-boundary enforcement for the C1 controller.
    controller_local_only_enforced: bool = False
    controller_external_routes_refused: int = 0
    controller_route_class: str = ""
    controller_endpoint_base_url: str = ""
    controller_missing_fields: list[str] = Field(default_factory=list)
    trajectory_relative_path: str = ""
    artifact_digest: str = ""
    created_at: str = ""
    allow_repo_write: bool = False
    allow_network: bool = False
    allow_secret_paths: bool = False
    require_evidence_citations: bool = True
