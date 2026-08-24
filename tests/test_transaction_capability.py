"""Capability mint / one-shot consume / secret isolation."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from agent_control.transaction.capability import (
    CAPABILITY_ALREADY_CONSUMED,
    CapabilityAlreadyConsumed,
    FilesystemCapabilityStore,
    InMemoryCapabilityStore,
    consume_capability,
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
    stored = store.get(cap.capability_id)
    assert stored is not None
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
    assert result["status"] == "CONSUMED"
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

    threads = [threading.Thread(target=_run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results.count("ok") == 1
    assert errors.count(CAPABILITY_ALREADY_CONSUMED) == 1


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
