"""Observation projection builder from ledger + session artifacts (V6 T01)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_control.events import load_project_events
from agent_control.session.storage import load_session, load_session_by_run
from agent_shared.models.observation_projection import ObservationProjection, ObservationStage

SESSION_EVENT_TYPES = frozenset(
    {
        "agent.session_started",
        "agent.subject_context_resolved",
        "agent.memory_preflight_created",
        "agent.context_packet_created",
        "agent.session_finished",
        "agent.session_failed",
        "agent.session_blocked",
        "agent.control_decision",
        "agent.run_completed",
    }
)


def _events_for_run(events: list[dict[str, Any]], run_id: str, session_id: str | None) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    for ev in events:
        payload = ev.get("payload") or {}
        rid = payload.get("run_id") or ev.get("run_id")
        sid = payload.get("session_id")
        if rid == run_id or (session_id and sid == session_id):
            matched.append(ev)
    matched.sort(key=lambda e: (e.get("recorded_at") or "", e.get("event_id") or ""))
    return matched


def build_observation_projection(
    state_root: Path,
    *,
    project: str,
    run_id: str | None = None,
    session_id: str | None = None,
) -> ObservationProjection:
    session = None
    if run_id:
        session = load_session_by_run(state_root, project, run_id)
    if session is None and session_id:
        session = load_session(state_root, project, session_id)

    rid = run_id or (session.run_ids[0] if session and session.run_ids else None)
    sid = session.session_id if session else session_id
    trace_id = session.trace_id if session else None

    all_events = load_project_events(state_root, project)
    timeline = _events_for_run(all_events, rid or "", sid) if rid or sid else []

    sequenced: list[dict[str, Any]] = []
    for idx, ev in enumerate(timeline, start=1):
        item = {
            "sequence": idx,
            "event_id": ev.get("event_id"),
            "type": ev.get("type"),
            "recorded_at": ev.get("recorded_at"),
            "payload": ev.get("payload"),
        }
        sequenced.append(item)

    stages: list[ObservationStage] = []
    types_present = {ev.get("type") for ev in timeline}

    def stage(name: str, required_types: set[str]) -> ObservationStage:
        present = required_types & types_present
        status = "present" if present == required_types else ("partial" if present else "missing")
        return ObservationStage(
            name=name,
            status=status,  # type: ignore[arg-type]
            sequence=max((s.sequence for s in stages), default=0) + 1,
            detail={"event_types": sorted(present)},
        )

    stages.append(stage("session", {"agent.session_started"}))
    stages.append(stage("context", {"agent.memory_preflight_created", "agent.context_packet_created"}))
    stages.append(stage("decisions", {"agent.control_decision"}))
    stages.append(
        stage(
            "terminal",
            {"agent.session_finished", "agent.session_failed", "agent.session_blocked", "agent.run_completed"},
        )
    )

    terminal = types_present & {
        "agent.session_finished",
        "agent.session_failed",
        "agent.session_blocked",
        "agent.run_completed",
    }
    complete = bool(terminal) and stages[0].status != "missing"

    return ObservationProjection(
        session_id=sid,
        run_id=rid,
        trace_id=trace_id,
        project=project,
        command_kind=session.command_kind if session else None,
        status=session.status.value if session else None,
        max_sequence=len(sequenced),
        stages=stages,
        events=sequenced,
        complete=complete,
    )
