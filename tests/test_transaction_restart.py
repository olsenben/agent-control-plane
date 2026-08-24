"""Restart / recovery: filesystem persist, reload, no duplicate / lost / reuse."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

from agent_control.ci.pending import load_pending_ci
from agent_control.events import load_project_events
from agent_control.publish.broker import broker_publish_fix
from agent_control.publish.pdp import (
    capability_store,
    run_publish_pdp,
    transaction_dir,
    witness_and_consume,
)
from agent_control.publish.state import load_publish_record
from agent_control.transaction.admission import AUTO_ADMIT, ESCALATE, REJECT
from agent_control.transaction.capability import (
    CAPABILITY_ALREADY_CONSUMED,
    CapabilityAlreadyConsumed,
    FilesystemCapabilityStore,
    consume_capability,
    mint_capability,
)
from agent_control.transaction.identity import fixture_actor_identity, human_initiator
from agent_shared.bundles.inbox import bundle_dir
from test_transaction_broker import (
    BASE_SHA,
    CORE,
    PROJECT,
    _pdp_result,
    _seed_publish,
    _validated,
)

DIGEST = "d" * 64
POLICY = "e" * 64
BUNDLE = "2" * 64


def _results_dir() -> Path | None:
    raw = os.environ.get("W5_ACCEPT_RESULTS_DIR")
    return Path(raw) if raw else None


def _append_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: set[str] = set()
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                existing.add(line)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            line = json.dumps(row, sort_keys=True)
            if line not in existing:
                handle.write(line + "\n")
                existing.add(line)


def _capture_samples(state: Path) -> None:
    dest = _results_dir()
    if dest is None:
        return
    events = load_project_events(state, PROJECT)
    tx_rows = [
        item
        for item in events
        if str(item.get("type") or "")
        in {
            "software_transaction.v1",
            "patch_admission_decision.v1",
            "durable_patch_capability.v1",
            "admission_escalation.v1",
        }
    ]
    _append_jsonl(dest / "transaction_event_log.jsonl", tx_rows)
    graph_rows: list[dict] = []
    for path in state.rglob("transaction_graph_edges.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                graph_rows.append(json.loads(line))
    if graph_rows:
        _append_jsonl(dest / "transaction_graph_capture.jsonl", graph_rows)


def _mint_fs(store: FilesystemCapabilityStore, **overrides: object):
    kwargs = {
        "repo": PROJECT,
        "tenant_id": "ai-sdlc-lab",
        "org_id": "ai-sdlc-lab",
        "source_sha": BASE_SHA,
        "patch_digest": DIGEST,
        "allowed_target_branch": "agent/admitted",
        "policy_digest": POLICY,
        "verification_digest": "f" * 64,
        "admission_decision_digest": "1" * 64,
        "evidence_bundle_digest": BUNDLE,
        "task_id": "task-1",
        "session_id": "sess-1",
        "human_initiator": human_initiator("alice"),
        "agent_identity": fixture_actor_identity(run_id="r1"),
        "store": store,
    }
    kwargs.update(overrides)
    return mint_capability(**kwargs)  # type: ignore[arg-type]


def test_restart_after_capability_issuance_no_reuse(tmp_path: Path) -> None:
    root = tmp_path / "caps"
    first = FilesystemCapabilityStore(root)
    cap = _mint_fs(first)
    cap_id = cap.capability_id
    # Simulate process restart: new store object, same filesystem tree.
    restarted = FilesystemCapabilityStore(root)
    loaded = restarted.get(cap_id)
    assert loaded is not None
    assert loaded.get("consumed") is not True
    assert loaded["source_sha"] == BASE_SHA
    consume_capability(
        capability_id=cap_id,
        store=restarted,
        current_base_sha=BASE_SHA,
        patch_digest=DIGEST,
        repo=PROJECT,
        target_ref="agent/admitted",
        policy_digest=POLICY,
        evidence_bundle_digest=BUNDLE,
    )
    after = FilesystemCapabilityStore(root)
    reused = after.get(cap_id)
    assert reused is not None
    assert reused.get("consumed") is True
    try:
        consume_capability(
            capability_id=cap_id,
            store=after,
            current_base_sha=BASE_SHA,
            patch_digest=DIGEST,
            repo=PROJECT,
            target_ref="agent/admitted",
            policy_digest=POLICY,
        )
        raise AssertionError("reused capability after restart")
    except CapabilityAlreadyConsumed as exc:
        assert exc.code == CAPABILITY_ALREADY_CONSUMED


def test_restart_before_publish_capability_intact(tmp_path: Path) -> None:
    root = tmp_path / "caps"
    minted = FilesystemCapabilityStore(root)
    cap = _mint_fs(minted, session_id="sess-before-publish")
    restarted = FilesystemCapabilityStore(root)
    loaded = restarted.get(cap.capability_id)
    assert loaded is not None
    assert loaded.get("consumed") is not True
    result = consume_capability(
        capability_id=cap.capability_id,
        store=restarted,
        current_base_sha=BASE_SHA,
        patch_digest=DIGEST,
        repo=PROJECT,
        target_ref="agent/admitted",
        policy_digest=POLICY,
        evidence_bundle_digest=BUNDLE,
    )
    assert result["allowed"] is True
    assert result["status"] == "CONSUMED"


def test_restart_preserves_admission_decision(tmp_path: Path, monkeypatch) -> None:
    state, manifest, result = _pdp_result(tmp_path, monkeypatch, run_id="run-rst-dec")
    assert result.decision == AUTO_ADMIT
    digest = result.admission.decision_digest
    cap_id = result.capability.capability_id if result.capability is not None else None
    assert cap_id
    store_dir = transaction_dir(state, PROJECT, result.proposal.session_id)
    admission_files = list((store_dir / "admission").glob("*.json"))
    assert admission_files
    # New process: new capability store over the same state root.
    reloaded_store = capability_store(state)
    reloaded_cap = reloaded_store.get(cap_id)
    assert reloaded_cap is not None
    assert reloaded_cap.get("consumed") is not True
    again = run_publish_pdp(
        state_root=state,
        project=PROJECT,
        run_id="run-rst-dec",
        bundle_id=manifest.bundle_id,
        bundle_root=bundle_dir(
            state, run_id="run-rst-dec", kind="fix", attempt_id="1", bundle_id=manifest.bundle_id
        ),
        manifest=manifest,
        authorized_files=[CORE],
        source_sha=BASE_SHA,
        agent_branch="agent/run-rst-dec",
        invoked_by="ai-sdlc-lab",
    )
    assert again.decision == AUTO_ADMIT
    assert again.admission.decision_digest == digest
    assert again.capability is not None
    assert again.capability.capability_id == cap_id
    events = [
        item
        for item in load_project_events(state, PROJECT)
        if item.get("type") == "software_transaction.v1"
    ]
    tx_ids = {item["payload"]["transaction_id"] for item in events}
    seqs = {(item["payload"]["transaction_id"], item["payload"]["event_seq"]) for item in events}
    assert len(tx_ids) == 1
    assert len(seqs) == len(events)
    _capture_samples(state)


def test_restart_after_publish_no_duplicate(tmp_path: Path, monkeypatch) -> None:
    state, manifest, settings = _seed_publish(
        tmp_path, monkeypatch, run_id="run-rst-pub", files=[CORE], patch_path=CORE
    )
    validated = _validated(manifest, tmp_path)
    with (
        patch("agent_control.publish.broker.GiteaClient") as gitea,
        patch("agent_control.publish.broker.validate_and_commit", return_value=validated),
        patch("agent_control.publish.broker.push_commit") as push,
        patch(
            "agent_control.publish.broker.open_or_find_pr",
            return_value=(9, "http://gitea.local:3000/ai-sdlc-lab/demo-app/pulls/9", False),
        ),
        patch("agent_control.publish.broker.post_issue_comment"),
        patch("agent_control.session.verification.request_session_verification"),
    ):
        gitea.return_value.get_branch_sha.return_value = BASE_SHA
        first = broker_publish_fix(
            state_root=state,
            run_id="run-rst-pub",
            attempt_id="1",
            bundle_id=manifest.bundle_id,
            settings=settings,
        )
        rec = load_publish_record(state, "run-rst-pub", manifest.bundle_id)
        assert rec is not None
        assert rec.publish_state == "succeeded"
        cap_store = capability_store(state)
        cap_files = list(cap_store.root.glob("*.json"))
        assert cap_files
        # Process restart: reload publish record + capability store, retry broker.
        restarted_store = FilesystemCapabilityStore(cap_store.root)
        for path in cap_files:
            body = json.loads(path.read_text(encoding="utf-8"))
            reloaded = restarted_store.get(body["capability_id"])
            assert reloaded is not None
            assert reloaded.get("consumed") is True
        second = broker_publish_fix(
            state_root=state,
            run_id="run-rst-pub",
            attempt_id="1",
            bundle_id=manifest.bundle_id,
            settings=settings,
        )
    assert first["ok"] is True
    assert first["decision"] == AUTO_ADMIT
    assert second.get("idempotent") is True
    assert push.call_count == 1
    pending = load_pending_ci(state, PROJECT, "run-rst-pub")
    assert pending is not None
    assert pending.expected_head_commit_sha == "c" * 40
    _capture_samples(state)


def test_restart_escalate_decision_not_lost(tmp_path: Path, monkeypatch) -> None:
    state, manifest, settings = _seed_publish(
        tmp_path,
        monkeypatch,
        run_id="run-rst-esc",
        files=[CORE],
        patch_path="src/pkg/other.py",
    )
    with (
        patch("agent_control.publish.broker.GiteaClient") as gitea,
        patch("agent_control.publish.broker.push_commit") as push,
    ):
        gitea.return_value.get_branch_sha.return_value = BASE_SHA
        first = broker_publish_fix(
            state_root=state,
            run_id="run-rst-esc",
            attempt_id="1",
            bundle_id=manifest.bundle_id,
            settings=settings,
        )
        second = broker_publish_fix(
            state_root=state,
            run_id="run-rst-esc",
            attempt_id="1",
            bundle_id=manifest.bundle_id,
            settings=settings,
        )
    assert first["ok"] is False
    assert first["decision"] == ESCALATE
    assert first.get("escalation_id")
    assert second["ok"] is False
    assert second["decision"] == ESCALATE
    assert second.get("escalation_id") == first.get("escalation_id")
    push.assert_not_called()
    rec = load_publish_record(state, "run-rst-esc", manifest.bundle_id)
    assert rec is not None
    assert rec.publish_state == "rejected"
    store = capability_store(state)
    assert list(store.root.glob("*.json")) == []
    _capture_samples(state)


def test_restart_reject_decision_not_lost(tmp_path: Path, monkeypatch) -> None:
    state, manifest, settings = _seed_publish(
        tmp_path,
        monkeypatch,
        run_id="run-rst-rej",
        files=["README.md"],
        patch_path="README.md",
    )
    with (
        patch("agent_control.publish.broker.GiteaClient") as gitea,
        patch("agent_control.publish.broker.push_commit") as push,
    ):
        gitea.return_value.get_branch_sha.return_value = BASE_SHA
        first = broker_publish_fix(
            state_root=state,
            run_id="run-rst-rej",
            attempt_id="1",
            bundle_id=manifest.bundle_id,
            settings=settings,
        )
        second = broker_publish_fix(
            state_root=state,
            run_id="run-rst-rej",
            attempt_id="1",
            bundle_id=manifest.bundle_id,
            settings=settings,
        )
    assert first["ok"] is False
    assert first["decision"] == REJECT
    assert first.get("decision_digest")
    assert second["decision"] == REJECT
    assert second.get("decision_digest") == first.get("decision_digest")
    push.assert_not_called()
    store = capability_store(state)
    assert list(store.root.glob("*.json")) == []
    _capture_samples(state)


def test_restart_witness_after_reload_still_exact(tmp_path: Path, monkeypatch) -> None:
    _state, _manifest, result = _pdp_result(tmp_path, monkeypatch, run_id="run-rst-wit")
    restarted = capability_store(_state)
    result.store = restarted
    consumed = witness_and_consume(
        result,
        current_base_sha=BASE_SHA,
        patch_digest=result.patch_digest,
        repo=PROJECT,
        target_ref=result.allowed_target_branch,
        policy_digest=result.policy.policy_digest,
    )
    assert consumed["allowed"] is True
    again = witness_and_consume(
        result,
        current_base_sha=BASE_SHA,
        patch_digest=result.patch_digest,
        repo=PROJECT,
        target_ref=result.allowed_target_branch,
        policy_digest=result.policy.policy_digest,
    )
    assert again["allowed"] is False
    assert again["status"] == CAPABILITY_ALREADY_CONSUMED
    _capture_samples(_state)
