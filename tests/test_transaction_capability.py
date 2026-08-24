"""Capability mint / one-shot consume / secret isolation."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from agent_control.transaction.capability import (
    ALREADY_CLAIMED,
    CAPABILITY_ALREADY_CONSUMED,
    CAPABILITY_CONSUMING,
    LIFECYCLE_CONSUMED,
    LIFECYCLE_CONSUMING,
    LIFECYCLE_INVALIDATED,
    LIFECYCLE_MINTED,
    CapabilityAlreadyClaimed,
    CapabilityAlreadyConsumed,
    CapabilityNotConsuming,
    FilesystemCapabilityStore,
    InMemoryCapabilityStore,
    complete_consumed_capability,
    consume_capability,
    invalidate_capability,
    lifecycle_of,
    mint_capability,
    worker_facing_payload,
)
from agent_control.transaction.identity import fixture_actor_identity, human_initiator
from agent_control.transaction.witness import StateWitnessError

DIGEST = "d" * 64
SHA = "deadbee"


def _mint(store: InMemoryCapabilityStore, **overrides: object):
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


def test_mint_and_one_shot_consume() -> None:
    store = InMemoryCapabilityStore()
    cap = _mint(store)
    assert cap.consumed is False
    stored = store.get(cap.capability_id)
    assert stored is not None
    assert lifecycle_of(stored) == LIFECYCLE_MINTED
    assert stored["consumed"] is False
    assert "secret" in stored
    public = worker_facing_payload(stored)
    assert "secret" not in public
    result = consume_capability(
        capability_id=cap.capability_id,
        store=store,
        current_base_sha=SHA,
        patch_digest=DIGEST,
        repo="org/repo",
        target_ref="agent/admitted",
        policy_digest="e" * 64,
        evidence_bundle_digest="2" * 64,
    )
    assert result["status"] == CAPABILITY_CONSUMING
    stored_after = store.get(cap.capability_id)
    assert stored_after is not None
    assert lifecycle_of(stored_after) == LIFECYCLE_CONSUMING
    assert stored_after["consumed"] is False
    completed = complete_consumed_capability(capability_id=cap.capability_id, store=store)
    assert completed["status"] == "CONSUMED"
    stored_done = store.get(cap.capability_id)
    assert stored_done is not None
    assert lifecycle_of(stored_done) == LIFECYCLE_CONSUMED
    with pytest.raises(CapabilityAlreadyConsumed) as exc:
        consume_capability(
            capability_id=cap.capability_id,
            store=store,
            current_base_sha=SHA,
            patch_digest=DIGEST,
            repo="org/repo",
            target_ref="agent/admitted",
            policy_digest="e" * 64,
        )
    assert exc.value.code == CAPABILITY_ALREADY_CONSUMED


def test_concurrent_duplicate_consume() -> None:
    store = InMemoryCapabilityStore()
    cap = _mint(store)
    results: list[str] = []
    errors: list[str] = []
    barrier = threading.Barrier(2)

    def _run() -> None:
        barrier.wait()
        try:
            consume_capability(
                capability_id=cap.capability_id,
                store=store,
                current_base_sha=SHA,
                patch_digest=DIGEST,
                repo="org/repo",
                target_ref="agent/admitted",
                policy_digest="e" * 64,
                evidence_bundle_digest="2" * 64,
            )
            results.append("ok")
        except CapabilityAlreadyConsumed:
            errors.append(CAPABILITY_ALREADY_CONSUMED)
        except CapabilityAlreadyClaimed:
            errors.append(ALREADY_CLAIMED)

    threads = [threading.Thread(target=_run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    stored = store.get(cap.capability_id)
    assert stored is not None
    assert lifecycle_of(stored) == LIFECYCLE_CONSUMING
    assert stored["consumed"] is not True
    assert results.count("ok") == 1
    assert results.count("ok") + errors.count(CAPABILITY_ALREADY_CONSUMED) + errors.count(
        ALREADY_CLAIMED
    ) == 2


def test_filesystem_store_consume(tmp_path: Path) -> None:
    store = FilesystemCapabilityStore(tmp_path)
    cap = _mint(store)
    consume_capability(
        capability_id=cap.capability_id,
        store=store,
        current_base_sha=SHA,
        patch_digest=DIGEST,
        repo="org/repo",
        target_ref="agent/admitted",
        policy_digest="e" * 64,
        evidence_bundle_digest="2" * 64,
    )
    complete_consumed_capability(capability_id=cap.capability_id, store=store)
    with pytest.raises(CapabilityAlreadyConsumed):
        store.consume_atomic(cap.capability_id)


def test_consume_source_drift() -> None:
    store = InMemoryCapabilityStore()
    cap = _mint(store)
    with pytest.raises(StateWitnessError) as exc:
        consume_capability(
            capability_id=cap.capability_id,
            store=store,
            current_base_sha="other12",
            patch_digest=DIGEST,
            repo="org/repo",
            target_ref="agent/admitted",
            policy_digest="e" * 64,
        )
    assert exc.value.code == "SOURCE_DRIFT"


def test_lifecycle_persisted_and_duplicate_consume(tmp_path: Path) -> None:
    store = FilesystemCapabilityStore(tmp_path)
    cap = _mint(store)
    path = tmp_path / f"{cap.capability_id}.json"
    raw = path.read_text(encoding="utf-8")
    assert LIFECYCLE_MINTED in raw
    consume_capability(
        capability_id=cap.capability_id,
        store=store,
        current_base_sha=SHA,
        patch_digest=DIGEST,
        repo="org/repo",
        target_ref="agent/admitted",
        policy_digest="e" * 64,
        evidence_bundle_digest="2" * 64,
    )
    persisted = store.get(cap.capability_id)
    assert persisted is not None
    assert persisted["lifecycle"] == LIFECYCLE_CONSUMING
    assert persisted["consumed"] is False
    complete_consumed_capability(capability_id=cap.capability_id, store=store)
    persisted = store.get(cap.capability_id)
    assert persisted is not None
    assert persisted["lifecycle"] == LIFECYCLE_CONSUMED
    assert persisted["consumed"] is True
    with pytest.raises(CapabilityAlreadyConsumed) as exc:
        store.consume_atomic(cap.capability_id)
    assert exc.value.code == CAPABILITY_ALREADY_CONSUMED


def test_consuming_then_consumed_in_one_lock() -> None:
    store = InMemoryCapabilityStore()
    cap = _mint(store)
    record = store.get(cap.capability_id)
    assert record is not None
    record["lifecycle"] = LIFECYCLE_CONSUMING
    record["consumed"] = False
    store.put(record)
    consumed = store.consume_atomic(cap.capability_id)
    assert consumed["lifecycle"] == LIFECYCLE_CONSUMED
    assert consumed["consumed"] is True


def test_invalidate_prevents_consume() -> None:
    store = InMemoryCapabilityStore()
    cap = _mint(store)
    invalidate_capability(store, cap.capability_id)
    stored = store.get(cap.capability_id)
    assert stored is not None
    assert stored["lifecycle"] == LIFECYCLE_INVALIDATED
    with pytest.raises(CapabilityAlreadyConsumed):
        store.consume_atomic(cap.capability_id)


def test_consuming_persists_across_new_store(tmp_path: Path) -> None:
    first = FilesystemCapabilityStore(tmp_path)
    cap = _mint(first)
    begun = first.begin_consume_atomic(cap.capability_id)
    assert lifecycle_of(begun) == LIFECYCLE_CONSUMING
    restarted = FilesystemCapabilityStore(tmp_path)
    loaded = restarted.get(cap.capability_id)
    assert loaded is not None
    assert lifecycle_of(loaded) == LIFECYCLE_CONSUMING
    assert loaded["consumed"] is not True
    with pytest.raises(CapabilityAlreadyClaimed):
        restarted.begin_consume_atomic(cap.capability_id)
    completed = complete_consumed_capability(capability_id=cap.capability_id, store=restarted)
    assert completed["status"] == "CONSUMED"
    replayed = complete_consumed_capability(
        capability_id=cap.capability_id, store=FilesystemCapabilityStore(tmp_path)
    )
    assert replayed["status"] == "CONSUMED"
    assert replayed["receipt"]["replayed"] is True
    with pytest.raises(CapabilityAlreadyConsumed):
        consume_capability(
            capability_id=cap.capability_id,
            store=FilesystemCapabilityStore(tmp_path),
            current_base_sha=SHA,
            patch_digest=DIGEST,
            repo="org/repo",
            target_ref="agent/admitted",
            policy_digest="e" * 64,
        )


def test_complete_refuses_minted() -> None:
    store = InMemoryCapabilityStore()
    cap = _mint(store)
    with pytest.raises(CapabilityNotConsuming):
        store.complete_consume_atomic(cap.capability_id)


def test_concurrent_begin_consume_one_winner(tmp_path: Path) -> None:
    for store in (InMemoryCapabilityStore(), FilesystemCapabilityStore(tmp_path / "caps")):
        cap = _mint(store)
        n = 5
        barrier = threading.Barrier(n)
        outcomes: list[str] = []

        def _run(target_store: object = store) -> None:
            barrier.wait()
            try:
                record = target_store.begin_consume_atomic(cap.capability_id)  # type: ignore[attr-defined]
                outcomes.append(lifecycle_of(record))
            except CapabilityAlreadyConsumed:
                outcomes.append(CAPABILITY_ALREADY_CONSUMED)
            except CapabilityAlreadyClaimed:
                outcomes.append(ALREADY_CLAIMED)

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
        assert len(outcomes) == n
        assert all(
            item in {LIFECYCLE_CONSUMING, CAPABILITY_ALREADY_CONSUMED, ALREADY_CLAIMED}
            for item in outcomes
        )

