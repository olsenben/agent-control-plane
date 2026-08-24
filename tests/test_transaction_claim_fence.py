"""Atomic capability claim and refused-stale-event fencing."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from agent_control.transaction.barriers import (
    PHASE_MINT,
    PHASE_PUBLISH,
    REFUSED_REJECTED,
    DurableBarrierError,
    check_durable_effect_allowed,
    persist_reject_barrier,
    record_refused_stale_event,
    refused_stale_event_dir,
)
from agent_control.transaction.capability import (
    ALREADY_CLAIMED,
    INVALIDATED,
    LIFECYCLE_CONSUMING,
    CapabilityAlreadyClaimed,
    CapabilityInvalidated,
    FilesystemCapabilityStore,
    InMemoryCapabilityStore,
    invalidate_capability,
    lifecycle_of,
    mint_capability,
)
from agent_control.transaction.identity import fixture_actor_identity, human_initiator
from agent_control.transaction.inbound import process_inbound

DIGEST = "d" * 64
SHA = "deadbee"


def _mint(store, **overrides: object):
    kwargs = {
        "repo": "org/repo",
        "tenant_id": "t",
        "org_id": "o",
        "source_sha": SHA,
        "patch_digest": DIGEST,
        "allowed_target_branch": "agent/admitted",
        "policy_digest": "e" * 64,
        "verification_digest": "f" * 64,
        "admission_decision_digest": "1" * 64,
        "evidence_bundle_digest": "2" * 64,
        "task_id": "task-1",
        "session_id": "sess-1",
        "human_initiator": human_initiator("alice"),
        "agent_identity": fixture_actor_identity(run_id="r1"),
        "store": store,
    }
    kwargs.update(overrides)
    return mint_capability(**kwargs)  # type: ignore[arg-type]


def test_concurrent_begin_consume_exactly_one_winner(tmp_path: Path) -> None:
    store = FilesystemCapabilityStore(tmp_path / "caps")
    cap = _mint(store)
    n = 20
    barrier = threading.Barrier(n)
    outcomes: list[str] = []

    def _run() -> None:
        barrier.wait()
        try:
            record = store.begin_consume_atomic(cap.capability_id)
            outcomes.append(lifecycle_of(record))
        except CapabilityAlreadyClaimed as exc:
            outcomes.append(exc.code)

    threads = [threading.Thread(target=_run) for _ in range(n)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    persisted = store.get(cap.capability_id)
    assert persisted is not None
    assert lifecycle_of(persisted) == LIFECYCLE_CONSUMING
    assert persisted["consumed"] is not True
    assert outcomes.count(LIFECYCLE_CONSUMING) == 1
    assert outcomes.count(ALREADY_CLAIMED) == n - 1
    assert len(outcomes) == n


def test_already_consuming_second_caller_is_already_claimed() -> None:
    store = InMemoryCapabilityStore()
    cap = _mint(store)
    first = store.begin_consume_atomic(cap.capability_id)
    assert lifecycle_of(first) == LIFECYCLE_CONSUMING
    with pytest.raises(CapabilityAlreadyClaimed) as exc:
        store.begin_consume_atomic(cap.capability_id)
    assert exc.value.code == ALREADY_CLAIMED
    persisted = store.get(cap.capability_id)
    assert persisted is not None
    assert lifecycle_of(persisted) == LIFECYCLE_CONSUMING


def test_filesystem_already_consuming_is_already_claimed(tmp_path: Path) -> None:
    first = FilesystemCapabilityStore(tmp_path)
    cap = _mint(first)
    begun = first.begin_consume_atomic(cap.capability_id)
    assert lifecycle_of(begun) == LIFECYCLE_CONSUMING
    restarted = FilesystemCapabilityStore(tmp_path)
    with pytest.raises(CapabilityAlreadyClaimed) as exc:
        restarted.begin_consume_atomic(cap.capability_id)
    assert exc.value.code == ALREADY_CLAIMED


def test_invalidated_begin_consume_is_invalidated() -> None:
    store = InMemoryCapabilityStore()
    cap = _mint(store)
    invalidate_capability(store, cap.capability_id)
    with pytest.raises(CapabilityInvalidated) as exc:
        store.begin_consume_atomic(cap.capability_id)
    assert exc.value.code == INVALIDATED


def test_refused_stale_event_is_recorded_not_dropped(tmp_path: Path) -> None:
    persist_reject_barrier(tmp_path, run_id="run-stale", transaction_id="tx-stale")
    with pytest.raises(DurableBarrierError) as exc:
        check_durable_effect_allowed(
            tmp_path,
            run_id="run-stale",
            phase=PHASE_PUBLISH,
            event_id="evt-late-1",
            transaction_id="tx-stale",
            proposal_id="prop-1",
        )
    assert exc.value.code == REFUSED_REJECTED
    recorded = json.loads(
        (refused_stale_event_dir(tmp_path) / "evt-late-1.json").read_text(encoding="utf-8")
    )
    assert recorded["event_id"] == "evt-late-1"
    assert recorded["transaction_id"] == "tx-stale"
    assert recorded["proposal_id"] == "prop-1"
    assert recorded["reason"] == REFUSED_REJECTED
    assert "REJECTED" in recorded["current_state"]
    assert recorded["feeds_controller"] is False


def test_inbound_late_handler_refused_after_reject(tmp_path: Path) -> None:
    persist_reject_barrier(tmp_path, run_id="run-in", transaction_id="tx-in")
    calls = {"n": 0}

    def _mutate() -> dict[str, str]:
        calls["n"] += 1
        return {"mutated": "yes"}

    result = process_inbound(
        tmp_path,
        "admission",
        "evt-in-1",
        _mutate,
        run_id="run-in",
        transaction_id="tx-in",
        proposal_id="prop-in",
        phase=PHASE_MINT,
    )
    assert result["status"] == "REFUSED_STALE"
    assert result["event_id"] == "evt-in-1"
    assert result["transaction_id"] == "tx-in"
    assert result["proposal_id"] == "prop-in"
    assert calls["n"] == 0
    path = refused_stale_event_dir(tmp_path) / "evt-in-1.json"
    assert path.is_file()


def test_record_refused_stale_event_fields(tmp_path: Path) -> None:
    payload = record_refused_stale_event(
        tmp_path,
        event_id="e1",
        transaction_id="t1",
        proposal_id="p1",
        reason="REFUSED_REJECTED",
        current_state=["REJECTED"],
        run_id="r1",
        phase=PHASE_PUBLISH,
    )
    assert payload["event_id"] == "e1"
    assert payload["transaction_id"] == "t1"
    assert payload["proposal_id"] == "p1"
    assert payload["reason"] == "REFUSED_REJECTED"
    assert payload["current_state"] == ["REJECTED"]
