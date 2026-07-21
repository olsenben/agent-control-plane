"""Pre-session invocation + NL agent intent (V6 T07)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

InvocationStatus = Literal[
    "invocation_received",
    "intent_ambiguous",
    "intent_resolved",
    "clarification_requested",
    "clarification_received",
    "session_created",
    "invocation_rejected",
]


class AgentIntent(BaseModel):
    schema_version: str = "agent_intent.v1"
    kind: str | None = None
    natural_language_task: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    clarification_question: str | None = None
    extractor: str = "heuristic"


class InvocationRecord(BaseModel):
    schema_version: str = "invocation.v1"
    invocation_id: str
    project: str
    status: InvocationStatus = "invocation_received"
    source_comment_id: int | None = None
    source_delivery_id: str | None = None
    invocation_comment_id: int | None = None
    subject_number: int | None = None
    invoked_by: str = "unknown"
    raw_text: str = ""
    intent: AgentIntent | None = None
    session_id: str | None = None
    run_id: str | None = None
    created_at: str = ""
    updated_at: str = ""
