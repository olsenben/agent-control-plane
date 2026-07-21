"""Ledger helpers for injection assessment events (V6 T06)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from agent_control.events import AgentEvent, append_event, deterministic_event_id
from agent_control.project_identity import canonical_project
from agent_shared.models.injection_assessment import InjectionAssessment


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_injection_assessment(
    state_root: Path,
    assessment: InjectionAssessment,
) -> tuple[Path, bool]:
    delivery = (
        f"{assessment.session_id or 'none'}:{assessment.run_id or 'none'}:"
        f"{assessment.content_ref}:{assessment.risk}:{assessment.assessed_at}"
    )
    event_type = "agent.injection_assessment"
    event_id = deterministic_event_id("ct103", delivery, event_type)
    payload = assessment.model_dump(mode="json")
    # Hard invariant in the durable record.
    payload["authority_granted"] = False
    event = AgentEvent(
        event_id=event_id,
        type=event_type,
        raw_event_type=event_type,
        source="ct103",
        delivery_id=delivery,
        project=canonical_project(assessment.project or "unknown/unknown"),
        payload=payload,
        recorded_at=_now(),
    )
    return append_event(state_root, event)
