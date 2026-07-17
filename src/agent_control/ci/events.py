"""Append-only CI ledger events (Slice 6E.1)."""

from __future__ import annotations

from pathlib import Path

from agent_control.events import AgentEvent, append_event, deterministic_event_id
from agent_shared.models.ci import (
    FixCiFailureEvidenceCollectedEvent,
    FixCiFailureEvidenceUnavailableEvent,
    FixCiObservedEvent,
    FixCiRepairBlockedEvent,
    FixCiRepairExhaustedEvent,
    FixCiRepairPushedEvent,
    FixCiRepairRequestedEvent,
    FixCiRepairStartedEvent,
    FixCiRepairStaleEvent,
    FixCiVerdictChangedEvent,
)


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


def append_fix_ci_failure_evidence_collected(
    state_root: Path,
    body: FixCiFailureEvidenceCollectedEvent,
) -> tuple[Path, bool]:
    event_id = deterministic_event_id(
        "ct103",
        body.evidence_observation_id,
        "agent.fix_ci_failure_evidence_collected",
    )
    event = AgentEvent(
        event_id=event_id,
        type="agent.fix_ci_failure_evidence_collected",
        raw_event_type="agent.fix_ci_failure_evidence_collected",
        source="ct103",
        delivery_id=body.evidence_observation_id,
        project=body.repository,
        payload=body.model_dump(mode="json"),
    )
    return append_event(state_root, event)


def append_fix_ci_failure_evidence_unavailable(
    state_root: Path,
    body: FixCiFailureEvidenceUnavailableEvent,
) -> tuple[Path, bool]:
    event_id = deterministic_event_id(
        "ct103",
        body.evidence_observation_id,
        "agent.fix_ci_failure_evidence_unavailable",
    )
    event = AgentEvent(
        event_id=event_id,
        type="agent.fix_ci_failure_evidence_unavailable",
        raw_event_type="agent.fix_ci_failure_evidence_unavailable",
        source="ct103",
        delivery_id=body.evidence_observation_id,
        project=body.repository,
        payload=body.model_dump(mode="json"),
    )
    return append_event(state_root, event)


def append_fix_ci_repair_requested(
    state_root: Path,
    body: FixCiRepairRequestedEvent,
) -> tuple[Path, bool]:
    event_id = deterministic_event_id(
        "ct103",
        f"{body.repair_key}:{body.repair_attempt}:requested",
        "agent.fix_ci_repair_requested",
    )
    event = AgentEvent(
        event_id=event_id,
        type="agent.fix_ci_repair_requested",
        raw_event_type="agent.fix_ci_repair_requested",
        source="ct103",
        delivery_id=f"{body.repair_key}:{body.repair_attempt}",
        project=body.repository,
        payload=body.model_dump(mode="json"),
    )
    return append_event(state_root, event)


def append_fix_ci_repair_blocked(
    state_root: Path,
    body: FixCiRepairBlockedEvent,
) -> tuple[Path, bool]:
    reasons = ",".join(body.reason_codes[:8])
    event_id = deterministic_event_id(
        "ct103",
        f"{body.fix_run_id}:{body.expected_head_commit_sha}:{reasons}:blocked",
        "agent.fix_ci_repair_blocked",
    )
    event = AgentEvent(
        event_id=event_id,
        type="agent.fix_ci_repair_blocked",
        raw_event_type="agent.fix_ci_repair_blocked",
        source="ct103",
        delivery_id=f"{body.fix_run_id}:{body.expected_head_commit_sha}:blocked",
        project=body.repository,
        payload=body.model_dump(mode="json"),
    )
    return append_event(state_root, event)


def append_fix_ci_repair_started(
    state_root: Path,
    body: FixCiRepairStartedEvent,
) -> tuple[Path, bool]:
    event_id = deterministic_event_id(
        "ct103",
        f"{body.repair_key}:{body.repair_attempt}:started",
        "agent.fix_ci_repair_started",
    )
    event = AgentEvent(
        event_id=event_id,
        type="agent.fix_ci_repair_started",
        raw_event_type="agent.fix_ci_repair_started",
        source="ct103",
        delivery_id=f"{body.repair_key}:{body.repair_attempt}:started",
        project=body.repository,
        payload=body.model_dump(mode="json"),
    )
    return append_event(state_root, event)


def append_fix_ci_repair_pushed(
    state_root: Path,
    body: FixCiRepairPushedEvent,
) -> tuple[Path, bool]:
    event_id = deterministic_event_id(
        "ct103",
        f"{body.repair_key}:{body.new_head_commit_sha}:pushed",
        "agent.fix_ci_repair_pushed",
    )
    event = AgentEvent(
        event_id=event_id,
        type="agent.fix_ci_repair_pushed",
        raw_event_type="agent.fix_ci_repair_pushed",
        source="ct103",
        delivery_id=f"{body.repair_key}:{body.new_head_commit_sha}",
        project=body.repository,
        payload=body.model_dump(mode="json"),
    )
    return append_event(state_root, event)


def append_fix_ci_repair_exhausted(
    state_root: Path,
    body: FixCiRepairExhaustedEvent,
) -> tuple[Path, bool]:
    event_id = deterministic_event_id(
        "ct103",
        f"{body.fix_run_id}:exhausted:{body.repair_attempt}",
        "agent.fix_ci_repair_exhausted",
    )
    event = AgentEvent(
        event_id=event_id,
        type="agent.fix_ci_repair_exhausted",
        raw_event_type="agent.fix_ci_repair_exhausted",
        source="ct103",
        delivery_id=f"{body.fix_run_id}:exhausted",
        project=body.repository,
        payload=body.model_dump(mode="json"),
    )
    return append_event(state_root, event)


def append_fix_ci_repair_stale(
    state_root: Path,
    body: FixCiRepairStaleEvent,
) -> tuple[Path, bool]:
    event_id = deterministic_event_id(
        "ct103",
        f"{body.repair_key}:{body.repair_attempt}:{body.reason}:stale",
        "agent.fix_ci_repair_stale",
    )
    event = AgentEvent(
        event_id=event_id,
        type="agent.fix_ci_repair_stale",
        raw_event_type="agent.fix_ci_repair_stale",
        source="ct103",
        delivery_id=f"{body.repair_key}:stale:{body.reason}",
        project=body.repository,
        payload=body.model_dump(mode="json"),
    )
    return append_event(state_root, event)
