"""Model route attempt recording (V6 T04)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_control.events import AgentEvent, append_event, deterministic_event_id
from agent_control.project_identity import canonical_project

MODEL_ROUTE_ATTEMPTED = "agent.model_route_attempted"
MODEL_ROUTE_FAILED = "agent.model_route_failed"
MODEL_FALLBACK_SELECTED = "agent.model_fallback_selected"
MODEL_CALL_COMPLETED = "agent.model_call_completed"
MODEL_ALL_ROUTES_FAILED = "agent.model_all_routes_failed"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_model_route_event(
    state_root: Path,
    *,
    project: str,
    event_type: str,
    payload: dict[str, Any],
) -> tuple[Path, bool]:
    run_id = str(payload.get("run_id") or "none")
    attempt = str(payload.get("retry_number") or payload.get("attempt") or "0")
    delivery = f"{run_id}:{event_type}:{attempt}:{payload.get('provider') or 'none'}"
    event_id = deterministic_event_id("ct103", delivery, event_type)
    body = {
        "schema_version": "model_route_event.v1",
        "recorded_at": _now(),
        **payload,
    }
    event = AgentEvent(
        event_id=event_id,
        type=event_type,
        raw_event_type=event_type,
        source="ct103",
        delivery_id=delivery,
        project=canonical_project(project),
        payload=body,
        recorded_at=_now(),
    )
    return append_event(state_root, event)
