"""Idempotency: replay proposal / evidence / admission / broker / CI with same keys."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from agent_control.ci.events import append_fix_ci_verdict_changed
from agent_control.events import load_project_events
from agent_control.publish.broker import broker_publish_fix
from agent_control.publish.pdp import run_publish_pdp, transaction_dir
from agent_control.publish.state import load_publish_record
from agent_control.session.lifecycle import begin_typed_session
from agent_control.session.storage import load_session_by_run
from agent_control.session.verification import (
    apply_ci_verdict_to_session,
    request_session_verification,
)
from agent_control.transaction.admission import AUTO_ADMIT
from agent_control.transaction.identity import (
    attribution,
    control_plane,
    fixture_actor_identity,
    human_initiator,
)
from agent_control.transaction.ledger import append_software_transaction
from agent_control.transaction.proposal import finalize_proposal
from agent_shared.bundles.inbox import BundleError, write_ready_bundle
from agent_shared.models.ci import FixCiVerdictChangedEvent
from agent_shared.models.jobs import TriggerContext
from agent_shared.models.transaction.admission import EvidenceRef, TaskRef
from agent_shared.models.transaction.ledger import (
    ActorRef,
    DecisionRef,
    PatchRef,
    SoftwareTransaction,
)
from agent_workers.transaction.proposal import (
    WorkerProposalContext,
    build_finalized_worker_proposal,
    build_patch_proposal,
    proposal_json_bytes,
)
from test_transaction_broker import (
    BASE_SHA,
    CORE,
    PROJECT,
    _pdp_result,
    _seed_publish,
    _validated,
)
from test_transaction_worker_proposal import PATCH_A, PATCH_B

PIN_COMMIT = "aa" * 20


def _identity():
    return attribution(
        on_behalf_of=human_initiator("alice"),
        executed_by=fixture_actor_identity(),
        authorized_by=control_plane(),
    )


def test_replay_proposal_same_keys_no_duplicate(tmp_path: Path) -> None:
    context = WorkerProposalContext(
        session_id="sess-idem-1",
        repo="org/demo",
        task_id="task-1",
        tenant_id="org",
        org_id="org",
        human_initiator_id="alice",
        changed_symbols=["pkg.core.fix"],
    )
    first = build_finalized_worker_proposal(
        context=context,
        source_sha="abc1234def",
        patch_bytes=PATCH_A,
        source_tree="treesha40notdigest",
        finalized_at="2026-08-24T01:00:00+00:00",
    )
    second = finalize_proposal(first, finalized_at="2026-08-24T09:00:00+00:00")
    assert first.proposal_id == second.proposal_id
    assert first.patch_digest == second.patch_digest
    assert first.finalized_at == second.finalized_at
    manifest = write_ready_bundle(
        tmp_path,
        run_id="run-idem-prop",
        kind="fix",
        attempt_id="1",
        bundle_id="fixed-idem",
        producer_base_sha="abc1234def",
        patch_bytes=PATCH_A,
        producer_tree_sha="treesha40notdigest",
        proposal_payload=proposal_json_bytes(first),
    )
    with pytest.raises(BundleError, match="already exists"):
        write_ready_bundle(
            tmp_path,
            run_id="run-idem-prop",
            kind="fix",
            attempt_id="1",
            bundle_id="fixed-idem",
            producer_base_sha="abc1234def",
            patch_bytes=PATCH_B,
            producer_tree_sha="treesha40notdigest",
            proposal_payload=proposal_json_bytes(first),
        )
    assert manifest.bundle_id == "fixed-idem"


def test_replay_evidence_and_admission_same_keys(tmp_path: Path, monkeypatch) -> None:
    state, manifest, first = _pdp_result(tmp_path, monkeypatch, run_id="run-idem-pdp")
    from agent_shared.bundles.inbox import bundle_dir

    root = bundle_dir(
        state, run_id="run-idem-pdp", kind="fix", attempt_id="1", bundle_id=manifest.bundle_id
    )
    second = run_publish_pdp(
        state_root=state,
        project=PROJECT,
        run_id="run-idem-pdp",
        bundle_id=manifest.bundle_id,
        bundle_root=root,
        manifest=manifest,
        authorized_files=[CORE],
        source_sha=BASE_SHA,
        agent_branch="agent/run-idem-pdp",
        invoked_by="ai-sdlc-lab",
    )
    assert first.decision == AUTO_ADMIT
    assert second.decision == AUTO_ADMIT
    assert first.proposal.proposal_id == second.proposal.proposal_id
    assert first.evidence_bundle_digest == second.evidence_bundle_digest
    assert first.admission.decision_digest == second.admission.decision_digest
    assert first.capability is not None and second.capability is not None
    assert first.capability.capability_id == second.capability.capability_id
    store_dir = transaction_dir(state, PROJECT, first.proposal.session_id)
    evidence_files = list((store_dir / "evidence").glob("*.json"))
    admission_files = list((store_dir / "admission").glob("*.json"))
    cap_files = list((state / "transaction" / "capabilities").glob("*.json"))
    assert len(evidence_files) == 1
    assert len(admission_files) == 1
    assert len(cap_files) == 1
    events = [
        item
        for item in load_project_events(state, PROJECT)
        if item.get("type") in {"software_transaction.v1", "patch_admission_decision.v1"}
    ]
    decision_events = [item for item in events if item.get("type") == "patch_admission_decision.v1"]
    tx_events = [item for item in events if item.get("type") == "software_transaction.v1"]
    assert len(decision_events) == 1
    tx_keys = {(item["payload"]["transaction_id"], item["payload"]["event_seq"]) for item in tx_events}
    assert len(tx_keys) == len(tx_events)


def test_replay_broker_no_duplicate_publish(tmp_path: Path, monkeypatch) -> None:
    state, manifest, settings = _seed_publish(
        tmp_path, monkeypatch, run_id="run-idem-brk", files=[CORE], patch_path=CORE
    )
    validated = _validated(manifest, tmp_path)
    with (
        patch("agent_control.publish.broker.GiteaClient") as gitea,
        patch("agent_control.publish.broker.validate_and_commit", return_value=validated),
        patch("agent_control.publish.broker.push_commit") as push,
        patch(
            "agent_control.publish.broker.open_or_find_pr",
            return_value=(21, "http://gitea.local:3000/ai-sdlc-lab/demo-app/pulls/21", False),
        ),
        patch("agent_control.publish.broker.post_issue_comment"),
        patch("agent_control.session.verification.request_session_verification"),
    ):
        gitea.return_value.get_branch_sha.return_value = BASE_SHA
        first = broker_publish_fix(
            state_root=state,
            run_id="run-idem-brk",
            attempt_id="1",
            bundle_id=manifest.bundle_id,
            settings=settings,
        )
        second = broker_publish_fix(
            state_root=state,
            run_id="run-idem-brk",
            attempt_id="1",
            bundle_id=manifest.bundle_id,
            settings=settings,
        )
        third = broker_publish_fix(
            state_root=state,
            run_id="run-idem-brk",
            attempt_id="1",
            bundle_id=manifest.bundle_id,
            settings=settings,
        )
    assert first["ok"] is True
    assert second.get("idempotent") is True
    assert third.get("idempotent") is True
    assert push.call_count == 1
    rec = load_publish_record(state, "run-idem-brk", manifest.bundle_id)
    assert rec is not None
    assert rec.publish_state == "succeeded"


def test_replay_ledger_same_event_id(tmp_path: Path) -> None:
    tx = SoftwareTransaction(
        transaction_id="tx-idem",
        tenant_id="t",
        org_id="o",
        repository="org/repo",
        task=TaskRef(task_id="task-1", task_digest="a" * 64),
        actor=ActorRef(
            session_id="s1",
            actor_identity=_identity().EXECUTED_BY,
            worker_identity=_identity().EXECUTED_BY,
        ),
        patch=PatchRef(source_sha="abc1234", patch_digest="b" * 64),
        evidence=EvidenceRef(bundle_id="bun-1", bundle_digest="c" * 64),
        decision=DecisionRef(decision="AUTO_ADMIT", decision_digest="d" * 64),
        capability=None,
        durable_outcome="AUTO_ADMITTED_CAPABILITY_MINTED",
        identity=_identity(),
        recorded_at="2026-08-24T00:00:00+00:00",
        event_seq=1,
    )
    path, created = append_software_transaction(tmp_path, tx)
    path2, created2 = append_software_transaction(tmp_path, tx)
    path3, created3 = append_software_transaction(tmp_path, tx)
    assert created is True
    assert created2 is False
    assert created3 is False
    assert path == path2 == path3
    events = [
        item
        for item in load_project_events(tmp_path, "org/repo")
        if item.get("type") == "software_transaction.v1"
    ]
    assert len(events) == 1


def test_replay_ci_verdict_same_keys(tmp_path: Path) -> None:
    state = tmp_path / "agent-state"
    state.mkdir()
    session = begin_typed_session(
        state,
        project=PROJECT,
        command_kind="fix",
        run_id="run-idem-ci",
        head_sha=BASE_SHA,
        trigger_context=TriggerContext(
            event_type="gitea.issue_comment",
            issue_number=2,
            author="alice",
            raw_body="/agent fix",
            normalized_body="/agent fix",
        ),
    )
    request_session_verification(state, project=PROJECT, run_id="run-idem-ci", commit_sha=PIN_COMMIT)
    body = FixCiVerdictChangedEvent(
        fix_run_id="run-idem-ci",
        repository=PROJECT,
        expected_head_commit_sha=PIN_COMMIT,
        previous_verdict="pending",
        verdict="verified",
        verdict_revision=1,
        reason_codes=["required_workflows_passed"],
        evaluated_at="2026-08-24T00:00:00+00:00",
    )
    _path, created = append_fix_ci_verdict_changed(state, body)
    _path2, created2 = append_fix_ci_verdict_changed(state, body)
    assert created is True
    assert created2 is False
    apply_ci_verdict_to_session(
        state,
        project=PROJECT,
        fix_run_id="run-idem-ci",
        verdict="verified",
        previous_verdict="pending",
        expected_head_commit_sha=PIN_COMMIT,
        verdict_revision=1,
    )
    apply_ci_verdict_to_session(
        state,
        project=PROJECT,
        fix_run_id="run-idem-ci",
        verdict="verified",
        previous_verdict="pending",
        expected_head_commit_sha=PIN_COMMIT,
        verdict_revision=1,
    )
    loaded = load_session_by_run(state, PROJECT, "run-idem-ci")
    assert loaded is not None
    assert loaded.session_id == session.session_id
    types = [item["type"] for item in load_project_events(state, PROJECT)]
    assert types.count("agent.fix_ci_verdict_changed") == 1
    assert types.count("agent.verification_passed") <= 1


def test_unfinalized_proposal_replay_finalize_stable() -> None:
    draft = build_patch_proposal(
        session_id="sess-idem-2",
        repo="org/demo",
        task_id="task-1",
        source_sha="abc1234",
        patch_bytes=PATCH_A,
        raw_patch_location="patch.diff",
        tenant_id="org",
        org_id="org",
    )
    first = finalize_proposal(draft, finalized_at="2026-08-24T01:00:00+00:00")
    second = finalize_proposal(first, finalized_at="2026-08-24T09:00:00+00:00")
    assert first.proposal_id == second.proposal_id
    assert first.patch_digest == second.patch_digest
    assert first.finalized_at == second.finalized_at
