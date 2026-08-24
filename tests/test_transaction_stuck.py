"""Stuck-transaction detector. Surfaces STUCK_TRANSACTION; never auto-completes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from agent_control.transaction.stuck import (
    DEFAULT_SLA_SECONDS,
    STUCK_STATES,
    STUCK_TRANSACTION,
    StuckCandidate,
    detect_stuck_transactions,
)


def test_stuck_states_surface_without_auto_complete() -> None:
    now = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)
    candidates = [
        StuckCandidate(
            transaction_id=f"tx-{state}",
            state=state,
            updated_at=(now - timedelta(seconds=DEFAULT_SLA_SECONDS[state] + 10)).isoformat(),
            run_id=f"run-{state}",
        )
        for state in STUCK_STATES
    ]
    fresh = StuckCandidate(
        transaction_id="tx-fresh",
        state="PATCH_PROPOSED",
        updated_at=(now - timedelta(seconds=1)).isoformat(),
    )
    alerts = detect_stuck_transactions([*candidates, fresh], now=now)
    assert {item.state for item in alerts} == set(STUCK_STATES)
    assert all(item.code == STUCK_TRANSACTION for item in alerts)
    assert all(item.auto_completed is False for item in alerts)
    assert all(item.event is not None and item.event["event_type"] == STUCK_TRANSACTION for item in alerts)
    assert all(item.event["payload"]["auto_completed"] is False for item in alerts)
    assert "tx-fresh" not in {item.transaction_id for item in alerts}


def test_custom_sla_threshold() -> None:
    now = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)
    candidate = StuckCandidate(
        transaction_id="tx-1",
        state="ESCALATED",
        updated_at=(now - timedelta(seconds=30)).isoformat(),
    )
    none = detect_stuck_transactions([candidate], now=now, sla_seconds={"ESCALATED": 60})
    assert none == []
    alerts = detect_stuck_transactions([candidate], now=now, sla_seconds={"ESCALATED": 10})
    assert len(alerts) == 1
    assert alerts[0].state == "ESCALATED"
