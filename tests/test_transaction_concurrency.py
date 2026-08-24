"""Concurrency: two transactions on the same source SHA; first publish wins."""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

from agent_control.approval.storage import save_approval
from agent_control.publish.broker import broker_publish_fix
from agent_control.publish.envelope import bind_task_envelope_at_dispatch
from agent_control.publish.pdp import witness_and_consume
from agent_control.publish.state import load_publish_record, save_publish_record, try_enqueue_cas
from agent_control.session.lifecycle import begin_typed_session
from agent_control.transaction.admission import AUTO_ADMIT
from agent_shared.bundles.inbox import write_ready_bundle
from agent_shared.models.approval import WorkItemApproval
from agent_shared.models.jobs import RLMJob, TriggerContext
from test_transaction_broker import (
    BASE_SHA,
    CORE,
    PROJECT,
    _attestations,
    _patch_bytes,
    _pdp_result,
    _settings,
    _validated,
)

DRIFTED_SHA = "c" * 40


def _approval(run_id: str, files: list[str], *, target_id: str, approval_id: str) -> WorkItemApproval:
    return WorkItemApproval(
        approval_id=approval_id,
        approval_target_id=target_id,
        plan_alias="plan",
        plan_run_id=f"run-plan-{run_id}",
        plan_hash="ph",
        blast_radius_hash="bh",
        project=PROJECT,
        issue_id=7,
        allowed_files=files,
        approved_by_login="ai-sdlc-lab",
        approved_at="2026-01-01T00:00:00Z",
        expires_at="2099-01-01T00:00:00Z",
        status="reserved",
        reserved_by_fix_run_id=run_id,
        approved_base_sha=BASE_SHA,
        approved_base_ref="main",
    )


def _seed_named(
    tmp_path: Path,
    monkeypatch,
    *,
    run_id: str,
    target_id: str,
    bundle_id: str,
) -> tuple[Path, object, object]:
    settings = _settings(tmp_path, monkeypatch)
    state = settings.agent_state_root
    session = begin_typed_session(
        state,
        project=PROJECT,
        command_kind="fix",
        run_id=run_id,
        head_sha=BASE_SHA,
        trigger_context=TriggerContext(
            event_type="gitea.issue_comment",
            issue_number=7,
            author="ai-sdlc-lab",
            raw_body="/agent fix",
            normalized_body="/agent fix",
        ),
        invoked_by="ai-sdlc-lab",
        approved_by="ai-sdlc-lab",
    )
    job = MagicMock(spec=RLMJob)
    job.target_sha = BASE_SHA
    job.command_intent = MagicMock(
        kind="fix", natural_language_task="fix core", work_item_id=target_id
    )
    job.risk_class = "write_patch"
    job.fix_authorization = MagicMock(allowed_files=[CORE])
    bind_task_envelope_at_dispatch(state, session=session, job=job, changed_files=[CORE])
    manifest = write_ready_bundle(
        state,
        run_id=run_id,
        kind="fix",
        attempt_id="1",
        bundle_id=bundle_id,
        producer_base_sha=BASE_SHA,
        patch_bytes=_patch_bytes(CORE),
        extra_artifacts=_attestations(run_id, bundle_id),
        result_payload={"schema_version": "fix_result.v1", "files_changed": [CORE], "changes": []},
    )
    try_enqueue_cas(
        state,
        run_id=run_id,
        kind="fix",
        attempt_id="1",
        bundle_id=manifest.bundle_id,
        project=PROJECT,
    )
    rec = load_publish_record(state, run_id, manifest.bundle_id)
    assert rec is not None
    save_publish_record(
        state,
        rec.model_copy(update={"approval_target_id": target_id, "project": PROJECT}),
    )
    save_approval(state, _approval(run_id, [CORE], target_id=target_id, approval_id=f"appr-{run_id}"))
    return state, manifest, settings


def test_two_transactions_same_source_second_source_drift(
    tmp_path: Path, monkeypatch
) -> None:
    _state_a, _manifest_a, first = _pdp_result(tmp_path, monkeypatch, run_id="run-c1a")
    _state_b, _manifest_b, second = _pdp_result(tmp_path, monkeypatch, run_id="run-c1b")
    assert first.decision == AUTO_ADMIT
    assert second.decision == AUTO_ADMIT
    assert first.proposal.source_sha == second.proposal.source_sha == BASE_SHA
    won = witness_and_consume(
        first,
        current_base_sha=BASE_SHA,
        patch_digest=first.patch_digest,
        repo=PROJECT,
        target_ref=first.allowed_target_branch,
        policy_digest=first.policy.policy_digest,
    )
    assert won["allowed"] is True
    drifted = witness_and_consume(
        second,
        current_base_sha=DRIFTED_SHA,
        patch_digest=second.patch_digest,
        repo=PROJECT,
        target_ref=second.allowed_target_branch,
        policy_digest=second.policy.policy_digest,
    )
    assert drifted["allowed"] is False
    assert drifted["status"] in {"SOURCE_DRIFT", "STATE_WITNESS_MISMATCH"}
    leftover = second.store.get(second.capability.capability_id)
    assert leftover is not None
    assert leftover.get("consumed") is not True


def test_broker_second_transaction_source_drift_no_silent_rebase(
    tmp_path: Path, monkeypatch
) -> None:
    state, first_manifest, settings = _seed_named(
        tmp_path, monkeypatch, run_id="run-conc-a", target_id="tgt-a", bundle_id="bundle-a"
    )
    _state, second_manifest, _settings_obj = _seed_named(
        tmp_path, monkeypatch, run_id="run-conc-b", target_id="tgt-b", bundle_id="bundle-b"
    )
    assert _state == state
    validated_a = _validated(first_manifest, tmp_path)
    validated_b = _validated(second_manifest, tmp_path)
    remote_sha = {"value": BASE_SHA}

    def _branch_sha(*_args, **_kwargs):
        return remote_sha["value"]

    def _push(*_args, **_kwargs):
        remote_sha["value"] = DRIFTED_SHA
        return None

    with (
        patch("agent_control.publish.broker.GiteaClient") as gitea,
        patch(
            "agent_control.publish.broker.validate_and_commit",
            side_effect=[validated_a, validated_b],
        ),
        patch("agent_control.publish.broker.push_commit", side_effect=_push) as push,
        patch(
            "agent_control.publish.broker.open_or_find_pr",
            return_value=(11, "http://gitea.local:3000/ai-sdlc-lab/demo-app/pulls/11", False),
        ),
        patch("agent_control.publish.broker.post_issue_comment"),
        patch("agent_control.session.verification.request_session_verification"),
    ):
        gitea.return_value.get_branch_sha.side_effect = _branch_sha
        first = broker_publish_fix(
            state_root=state,
            run_id="run-conc-a",
            attempt_id="1",
            bundle_id=first_manifest.bundle_id,
            settings=settings,
        )
        second = broker_publish_fix(
            state_root=state,
            run_id="run-conc-b",
            attempt_id="1",
            bundle_id=second_manifest.bundle_id,
            settings=settings,
        )
    assert first["ok"] is True
    assert first["decision"] == AUTO_ADMIT
    assert second["ok"] is False
    assert second.get("reason") in {
        "SOURCE_DRIFT",
        "STATE_WITNESS_MISMATCH",
        "authorization_denied",
        "stale_base",
    }
    assert push.call_count == 1
    for call in push.call_args_list:
        kwargs = call.kwargs
        assert kwargs.get("force") in (None, False)
        args_flat = " ".join(str(item) for item in call.args)
        assert "--force" not in args_flat
        assert "rebase" not in args_flat.lower()
    rec_b = load_publish_record(state, "run-conc-b", second_manifest.bundle_id)
    assert rec_b is not None
    assert rec_b.publish_state in {"rejected", "failed_terminal"}


def test_concurrent_two_transactions_at_most_one_push(tmp_path: Path, monkeypatch) -> None:
    state, first_manifest, settings = _seed_named(
        tmp_path, monkeypatch, run_id="run-race-a", target_id="tgt-ra", bundle_id="bundle-ra"
    )
    _state, second_manifest, _settings_obj = _seed_named(
        tmp_path, monkeypatch, run_id="run-race-b", target_id="tgt-rb", bundle_id="bundle-rb"
    )
    validated_a = _validated(first_manifest, tmp_path)
    validated_b = _validated(second_manifest, tmp_path)
    lock = threading.Lock()
    remote_sha = {"value": BASE_SHA}
    push_count = {"n": 0}

    def _branch_sha(*_args, **_kwargs):
        with lock:
            return remote_sha["value"]

    def _push(*_args, **_kwargs):
        with lock:
            push_count["n"] += 1
            remote_sha["value"] = DRIFTED_SHA
        return None

    def _validate(*, settings, snapshot_dir, manifest, **_kwargs):
        if manifest.bundle_id == first_manifest.bundle_id:
            return validated_a
        return validated_b

    outcomes: dict[str, dict] = {}

    def _run(run_id: str, bundle_id: str) -> None:
        outcomes[run_id] = broker_publish_fix(
            state_root=state,
            run_id=run_id,
            attempt_id="1",
            bundle_id=bundle_id,
            settings=settings,
        )

    with (
        patch("agent_control.publish.broker.GiteaClient") as gitea,
        patch("agent_control.publish.broker.validate_and_commit", side_effect=_validate),
        patch("agent_control.publish.broker.push_commit", side_effect=_push) as push,
        patch(
            "agent_control.publish.broker.open_or_find_pr",
            return_value=(12, "http://gitea.local:3000/ai-sdlc-lab/demo-app/pulls/12", False),
        ),
        patch("agent_control.publish.broker.post_issue_comment"),
        patch("agent_control.session.verification.request_session_verification"),
    ):
        gitea.return_value.get_branch_sha.side_effect = _branch_sha
        threads = [
            threading.Thread(target=_run, args=("run-race-a", first_manifest.bundle_id)),
            threading.Thread(target=_run, args=("run-race-b", second_manifest.bundle_id)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    oks = [item.get("ok") is True for item in outcomes.values()]
    assert oks.count(True) == 1
    assert push.call_count == 1
    assert push_count["n"] == 1
    lost = [item for item in outcomes.values() if item.get("ok") is not True]
    assert lost
    assert lost[0].get("reason") in {
        "SOURCE_DRIFT",
        "STATE_WITNESS_MISMATCH",
        "authorization_denied",
        "CAPABILITY_ALREADY_CONSUMED",
        "stale_base",
    }
