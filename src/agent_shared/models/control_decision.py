"""CT103 deterministic control decisions (V6 T01)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ControlDecisionKind = Literal[
    "recursive_context_skipped",
    "sandbox_denied",
    "model_fallback_selected",
    "approval_required",
    "patch_rejected",
    "ci_verdict_accepted",
    "memory_governance_denied",
    "policy_denied",
    "other",
]


class ControlDecision(BaseModel):
    """Auditable CT103 control-plane decision — not model reasoning."""

    schema_version: str = "control_decision.v1"
    decision_id: str
    kind: ControlDecisionKind
    summary: str
    session_id: str | None = None
    run_id: str | None = None
    trace_id: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    policy_source_sha: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    recorded_at: str
