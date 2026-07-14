"""Append-only CI ledger events (Slice 6E.1)."""

from __future__ import annotations

from pathlib import Path

from agent_control.events import AgentEvent, append_event, deterministic_event_id
from agent_shared.models.ci import FixCiObservedEvent, FixCiVerdictChangedEvent


def append_fix_ci_observed(
    state_root: Path,
    body: FixCiObservedEvent,
) -> tuple[Path, bool]:
    """Idempotent by delivery_id + workflow_run_id + attempt + status."""
    obs = body.observation
    delivery = body.delivery_id or (
        f"{obs.workflow_run_id}:{obs.run_attempt}:{obs.status}:{obs.conclusion}"
    )
    event_id = deterministic_event_id(
        "ct103",
        f"{body.fix_run_id}:{delivery}",
        "agent.fix_ci_observed",
    )
    event = AgentEvent(
        event_id=event_id,
        type="agent.fix_ci_observed",
        raw_event_type="agent.fix_ci_observed",
        source="ct103",
        delivery_id=str(delivery),
        project=body.repository,
        payload=body.model_dump(mode="json"),
    )
    return append_event(state_root, event)


def append_fix_ci_verdict_changed(
    state_root: Path,
    body: FixCiVerdictChangedEvent,
) -> tuple[Path, bool]:
    """Idempotent by fix_run_id + verdict_revision."""
    event_id = deterministic_event_id(
        "ct103",
        f"{body.fix_run_id}:rev{body.verdict_revision}:{body.verdict}",
        "agent.fix_ci_verdict_changed",
    )
    event = AgentEvent(
        event_id=event_id,
        type="agent.fix_ci_verdict_changed",
        raw_event_type="agent.fix_ci_verdict_changed",
        source="ct103",
        delivery_id=f"{body.fix_run_id}:rev{body.verdict_revision}",
        project=body.repository,
        payload=body.model_dump(mode="json"),
    )
    return append_event(state_root, event)
