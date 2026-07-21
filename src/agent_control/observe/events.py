"""Control decision ledger events (V6 T01)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_control.events import AgentEvent, append_event, deterministic_event_id
from agent_control.project_identity import canonical_project
from agent_shared.models.control_decision import ControlDecision, ControlDecisionKind


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_control_decision(
    state_root: Path,
    *,
    project: str,
    kind: ControlDecisionKind,
    summary: str,
    session_id: str | None = None,
    run_id: str | None = None,
    trace_id: str | None = None,
    evidence_refs: list[str] | None = None,
    policy_source_sha: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> tuple[Path, bool]:
    decision_id = f"dec-{uuid.uuid4().hex[:16]}"
    body = ControlDecision(
        decision_id=decision_id,
        kind=kind,
        summary=summary,
        session_id=session_id,
        run_id=run_id,
        trace_id=trace_id,
        evidence_refs=list(evidence_refs or []),
        policy_source_sha=policy_source_sha,
        metadata=dict(metadata or {}),
        recorded_at=_now(),
    )
    delivery = f"{session_id or 'none'}:{run_id or 'none'}:{kind}:{decision_id}"
    event_id = deterministic_event_id("ct103", delivery, "agent.control_decision")
    event = AgentEvent(
        event_id=event_id,
        type="agent.control_decision",
        raw_event_type="agent.control_decision",
        source="ct103",
        delivery_id=delivery,
        project=canonical_project(project),
        payload=body.model_dump(mode="json"),
        recorded_at=_now(),
    )
    return append_event(state_root, event)
