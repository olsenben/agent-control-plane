"""Tests for durable repair reservation + lease."""

from __future__ import annotations

from pathlib import Path

from agent_control.ci.reservation import (
    RepairReservation,
    acquire_repair_lease,
    create_repair_reservation,
    heartbeat_repair_lease,
    load_repair_reservation,
    release_repair_lease,
)


def test_reservation_unique(tmp_path: Path) -> None:
    r = RepairReservation(
        repair_key="repair:o/r:1:abc",
        repository="o/r",
        pr_number=1,
        expected_head_commit_sha="abc",
        repair_attempt=1,
        fix_run_id="run-1",
        repair_lineage_id="run-1",
        evidence_observation_id="e1",
        agent_branch="agent/run-1",
        required_command_ids=["pytest_narrow"],
    )
    assert create_repair_reservation(tmp_path, r) is not None
    assert create_repair_reservation(tmp_path, r) is None
    loaded = load_repair_reservation(tmp_path, r.repair_key)
    assert loaded is not None
    assert loaded.repair_attempt == 1


def test_lease_expires_and_reclaim(tmp_path: Path, monkeypatch) -> None:
    key = "repair:o/r:1:abc"
    lease = acquire_repair_lease(tmp_path, key, holder="w1", ttl_seconds=60)
    assert lease is not None
    assert acquire_repair_lease(tmp_path, key, holder="w2", ttl_seconds=60) is None
    # Force expiry
    import json
    import time

    data = json.loads(lease.read_text(encoding="utf-8"))
    data["expires_at"] = time.time() - 1
    lease.write_text(json.dumps(data), encoding="utf-8")
    lease2 = acquire_repair_lease(tmp_path, key, holder="w2", ttl_seconds=60)
    assert lease2 is not None
    assert heartbeat_repair_lease(lease2)
    release_repair_lease(lease2)
