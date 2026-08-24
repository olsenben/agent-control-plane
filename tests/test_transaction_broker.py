"""Broker PDP/PEP wiring: three outcomes + TB3-TB10 without live Gitea."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from agent_control.approval.storage import load_approval, save_approval
from agent_control.ci.pending import load_pending_ci
from agent_control.config import Settings
from agent_control.publish.broker import broker_publish_fix
from agent_control.publish.envelope import bind_task_envelope_at_dispatch, load_task_envelope
from agent_control.publish.pdp import (
    MODEL_SPECIFIC_CONTROL_LOGIC,
    SCANNER_SPECIFIC_ADMISSION_LOGIC,
    in_process_adapter_kwargs,
    run_publish_pdp,
    witness_and_consume,
)
from agent_control.publish.state import load_publish_record, save_publish_record, try_enqueue_cas
from agent_control.session.lifecycle import begin_typed_session
from agent_control.transaction.admission import AUTO_ADMIT, ESCALATE, FROZEN_C_HASH, REJECT
from agent_control.transaction.capability import CAPABILITY_ALREADY_CONSUMED
from agent_control.transaction.evidence.adapters import actor_provided_receipt
from agent_shared.bundles.inbox import write_ready_bundle
from agent_shared.models.approval import WorkItemApproval
from agent_shared.models.attestation import ExecutionAttestationV1, SandboxAttestationV1
from agent_shared.models.jobs import RLMJob, TriggerContext

PROJECT = "ai-sdlc-lab/demo-app"
BASE_SHA = "abc1234000000000000000000000000000000000"
CORE = "src/pkg/core.py"
PIN = "ad265893a9e7161ba8acd0c95e778738d92584eb310cb6bac85e89121f72098c"


def _settings(tmp_path: Path, monkeypatch) -> Settings:
    state = tmp_path / "agent-state"
    cache = tmp_path / "cache"
    state.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("AGENT_STATE_ROOT", str(state))
    monkeypatch.setenv("AGENT_CACHE_DIR", str(cache))
    monkeypatch.setenv("GITEA_BASE_URL", "http://gitea.local:3000")
    monkeypatch.setenv("GITEA_BOT_TOKEN", "tok")
    return Settings()


def _patch_bytes(path: str) -> bytes:
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        "@@ -1 +1,2 @@\n"
        " def foo():\n"
        "+    return 1\n"
    ).encode()


def _attestations(run_id: str, bundle_id: str) -> dict[str, bytes]:
    sandbox = SandboxAttestationV1(
        run_id=run_id,
        executor_id="test-exec",
        workspace_id="ws-1",
        sandbox_backend="sim",
        ready_verdict="ready",
        created_at="2026-08-24T00:00:00Z",
    )
    execution = ExecutionAttestationV1(
        run_id=run_id,
        executor_id="test-exec",
        workspace_id="ws-1",
        teardown_status="destroyed",
        bundle_id=bundle_id,
        created_at="2026-08-24T00:00:01Z",
    )
    return {
        "sandbox_attestation.v1.json": sandbox.model_dump_json().encode(),
        "execution_attestation.v1.json": execution.model_dump_json().encode(),
    }


def _session(state: Path, run_id: str):
    return begin_typed_session(
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


def _approval(run_id: str, files: list[str]) -> WorkItemApproval:
    return WorkItemApproval(
        approval_id="appr-1",
        approval_target_id="tgt-1",
        plan_alias="plan",
        plan_run_id="run-plan-1",
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


def _seed_publish(
    tmp_path: Path,
    monkeypatch,
    *,
    run_id: str,
    files: list[str],
    patch_path: str,
    bundle_id: str = "bundle1",
) -> tuple[Path, object, Settings]:
    settings = _settings(tmp_path, monkeypatch)
    state = settings.agent_state_root
    session = _session(state, run_id)
    job = MagicMock(spec=RLMJob)
    job.target_sha = BASE_SHA
    job.command_intent = MagicMock(kind="fix", natural_language_task="fix core", work_item_id="tgt-1")
    job.risk_class = "write_patch"
    job.fix_authorization = MagicMock(allowed_files=files)
    bind_task_envelope_at_dispatch(state, session=session, job=job, changed_files=files)
    manifest = write_ready_bundle(
        state,
        run_id=run_id,
        kind="fix",
        attempt_id="1",
        bundle_id=bundle_id,
        producer_base_sha=BASE_SHA,
        patch_bytes=_patch_bytes(patch_path),
        extra_artifacts=_attestations(run_id, bundle_id),
        result_payload={"schema_version": "fix_result.v1", "files_changed": files, "changes": []},
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
        rec.model_copy(update={"approval_target_id": "tgt-1", "project": PROJECT}),
    )
    save_approval(state, _approval(run_id, files))
    return state, manifest, settings


def _validated(manifest, tmp_path: Path):
    validated = MagicMock()
    validated.commit_sha = "c" * 40
    validated.patch_sha256 = manifest.patch_sha256
    validated.result_tree_sha = "d" * 40
    validated.workspace = tmp_path / "ws"
    validated.workspace.mkdir(parents=True, exist_ok=True)
    return validated


def test_flags_are_no() -> None:
    assert MODEL_SPECIFIC_CONTROL_LOGIC == "NO"
    assert SCANNER_SPECIFIC_ADMISSION_LOGIC == "NO"
    assert FROZEN_C_HASH == PIN
    text = Path(__file__).resolve().parents[1].joinpath(
        "src/agent_control/publish/pdp.py"
    ).read_text(encoding="utf-8")
    assert "from agent_control.gitea" not in text
    assert "GiteaClient" not in text
    assert "g0=[]" not in text
    from agent_control.transaction.admission import HARNESS_SPECIFIC_CONTROL_LOGIC

    assert HARNESS_SPECIFIC_CONTROL_LOGIC == "NO"


def test_task_envelope_bound_at_dispatch(tmp_path: Path, monkeypatch) -> None:
    settings = _settings(tmp_path, monkeypatch)
    state = settings.agent_state_root
    session = _session(state, "run-env")
    job = MagicMock(spec=RLMJob)
    job.target_sha = BASE_SHA
    job.command_intent = MagicMock(kind="fix", natural_language_task="fix core", work_item_id="tgt")
    job.risk_class = "write_patch"
    job.fix_authorization = MagicMock(allowed_files=[CORE])
    envelope = bind_task_envelope_at_dispatch(
        state, session=session, job=job, changed_files=[CORE]
    )
    loaded = load_task_envelope(state, PROJECT, session.session_id)
    assert loaded is not None
    assert loaded.task_id == envelope.task_id
    assert loaded.schema_version == "task_envelope.v1"
    assert CORE in loaded.authorized_files
    assert loaded.human_initiator.principal_kind == "HUMAN_INITIATOR"
    again = bind_task_envelope_at_dispatch(
        state, session=session, job=job, changed_files=["other.py"]
    )
    assert again.task_digest == envelope.task_digest


def test_auto_admit_mints_capability_and_publishes_once(tmp_path: Path, monkeypatch) -> None:
    state, manifest, settings = _seed_publish(
        tmp_path, monkeypatch, run_id="run-auto", files=[CORE], patch_path=CORE
    )
    validated = _validated(manifest, tmp_path)
    with (
        patch("agent_control.publish.broker.GiteaClient") as gitea,
        patch("agent_control.publish.broker.validate_and_commit", return_value=validated),
        patch("agent_control.publish.broker.push_commit") as push,
        patch(
            "agent_control.publish.broker.open_or_find_pr",
            return_value=(42, "http://gitea.local:3000/ai-sdlc-lab/demo-app/pulls/42", False),
        ),
        patch("agent_control.publish.broker.post_issue_comment"),
        patch("agent_control.session.verification.request_session_verification"),
    ):
        gitea.return_value.get_branch_sha.return_value = BASE_SHA
        out = broker_publish_fix(
            state_root=state,
            run_id="run-auto",
            attempt_id="1",
            bundle_id=manifest.bundle_id,
            settings=settings,
        )
        again = broker_publish_fix(
            state_root=state,
            run_id="run-auto",
            attempt_id="1",
            bundle_id=manifest.bundle_id,
            settings=settings,
        )
    assert out["ok"] is True
    assert out["decision"] == AUTO_ADMIT
    assert out["capability_id"]
    assert push.call_count == 1
    assert again.get("idempotent") is True
    pending = load_pending_ci(state, PROJECT, "run-auto")
    assert pending is not None
    assert pending.expected_head_commit_sha == "c" * 40
    assert pending.opened_pr_number == 42
    rec = load_publish_record(state, "run-auto", manifest.bundle_id)
    assert rec is not None
    assert rec.publish_state == "succeeded"
    events_dir = state / "projects" / "ai-sdlc-lab" / "demo-app" / "events"
    dumped = "\n".join(p.read_text(encoding="utf-8") for p in events_dir.rglob("*.json"))
    assert "software_transaction.v1" in dumped
    assert "durable_patch_capability.v1" in dumped
    feedback_files = list(
        (state / "projects" / "ai-sdlc-lab" / "demo-app" / "transaction").rglob(
            "admission_feedback.jsonl"
        )
    )
    assert feedback_files
    feedback_text = "\n".join(p.read_text(encoding="utf-8") for p in feedback_files)
    assert '"feeds_controller": false' in feedback_text


def test_escalate_writes_escalation_and_does_not_publish(tmp_path: Path, monkeypatch) -> None:
    state, manifest, settings = _seed_publish(
        tmp_path,
        monkeypatch,
        run_id="run-esc",
        files=[CORE],
        patch_path="src/pkg/other.py",
    )
    with (
        patch("agent_control.publish.broker.GiteaClient") as gitea,
        patch("agent_control.publish.broker.validate_and_commit") as validate,
        patch("agent_control.publish.broker.push_commit") as push,
        patch("agent_control.publish.broker.open_or_find_pr") as pr,
    ):
        gitea.return_value.get_branch_sha.return_value = BASE_SHA
        out = broker_publish_fix(
            state_root=state,
            run_id="run-esc",
            attempt_id="1",
            bundle_id=manifest.bundle_id,
            settings=settings,
        )
    assert out["ok"] is False
    assert out["decision"] == ESCALATE
    assert out["reason"] == "admission_escalate"
    assert "escalation_id" in out
    assert "admission_escalation" in out
    push.assert_not_called()
    pr.assert_not_called()
    validate.assert_not_called()
    rec = load_publish_record(state, "run-esc", manifest.bundle_id)
    assert rec is not None
    assert rec.publish_state == "rejected"
    assert load_pending_ci(state, PROJECT, "run-esc") is None


def test_reject_writes_decision_receipt_and_does_not_publish(tmp_path: Path, monkeypatch) -> None:
    state, manifest, settings = _seed_publish(
        tmp_path,
        monkeypatch,
        run_id="run-rej",
        files=["README.md"],
        patch_path="README.md",
    )
    with (
        patch("agent_control.publish.broker.GiteaClient") as gitea,
        patch("agent_control.publish.broker.push_commit") as push,
        patch("agent_control.publish.broker.open_or_find_pr") as pr,
    ):
        gitea.return_value.get_branch_sha.return_value = BASE_SHA
        out = broker_publish_fix(
            state_root=state,
            run_id="run-rej",
            attempt_id="1",
            bundle_id=manifest.bundle_id,
            settings=settings,
        )
    assert out["ok"] is False
    assert out["decision"] == REJECT
    assert out["reason"] == "admission_reject"
    assert out.get("decision_digest")
    push.assert_not_called()
    pr.assert_not_called()
    rec = load_publish_record(state, "run-rej", manifest.bundle_id)
    assert rec is not None
    assert rec.publish_state == "rejected"


def test_tb3_patch_changed_after_admission_does_not_publish(tmp_path: Path, monkeypatch) -> None:
    state, manifest, settings = _seed_publish(
        tmp_path, monkeypatch, run_id="run-tb3", files=[CORE], patch_path=CORE
    )
    drifted = _validated(manifest, tmp_path)
    drifted.patch_sha256 = "9" * 64
    with (
        patch("agent_control.publish.broker.GiteaClient") as gitea,
        patch("agent_control.publish.broker.validate_and_commit", return_value=drifted),
        patch("agent_control.publish.broker.push_commit") as push,
        patch("agent_control.publish.broker.open_or_find_pr") as pr,
    ):
        gitea.return_value.get_branch_sha.return_value = BASE_SHA
        out = broker_publish_fix(
            state_root=state,
            run_id="run-tb3",
            attempt_id="1",
            bundle_id=manifest.bundle_id,
            settings=settings,
        )
    assert out["ok"] is False
    assert out["reason"] == "PATCH_DRIFT"
    push.assert_not_called()
    pr.assert_not_called()


def test_tb4_double_consume_exactly_one_publish(tmp_path: Path, monkeypatch) -> None:
    state, manifest, settings = _seed_publish(
        tmp_path, monkeypatch, run_id="run-tb4", files=[CORE], patch_path=CORE
    )
    validated = _validated(manifest, tmp_path)
    with (
        patch("agent_control.publish.broker.GiteaClient") as gitea,
        patch("agent_control.publish.broker.validate_and_commit", return_value=validated),
        patch("agent_control.publish.broker.push_commit") as push,
        patch(
            "agent_control.publish.broker.open_or_find_pr",
            return_value=(7, "http://gitea.local:3000/ai-sdlc-lab/demo-app/pulls/7", False),
        ),
        patch("agent_control.publish.broker.post_issue_comment"),
        patch("agent_control.session.verification.request_session_verification"),
    ):
        gitea.return_value.get_branch_sha.return_value = BASE_SHA
        first = broker_publish_fix(
            state_root=state,
            run_id="run-tb4",
            attempt_id="1",
            bundle_id=manifest.bundle_id,
            settings=settings,
        )
        rec = load_publish_record(state, "run-tb4", manifest.bundle_id)
        assert rec is not None
        save_publish_record(state, rec.model_copy(update={"publish_state": "queued"}))
        approval = load_approval(state, PROJECT, "tgt-1")
        assert approval is not None
        save_approval(
            state,
            approval.model_copy(
                update={
                    "status": "reserved",
                    "claimed_at": None,
                    "claimed_by_publish_job_id": None,
                    "consumed_at": None,
                    "consumed_by_run_id": None,
                }
            ),
        )
        second = broker_publish_fix(
            state_root=state,
            run_id="run-tb4",
            attempt_id="1",
            bundle_id=manifest.bundle_id,
            settings=settings,
        )
    assert first["ok"] is True
    assert second["ok"] is False
    assert second["reason"] == CAPABILITY_ALREADY_CONSUMED
    assert push.call_count == 1


def _pdp_result(tmp_path: Path, monkeypatch, run_id: str = "run-pdp"):
    state, manifest, _settings_obj = _seed_publish(
        tmp_path, monkeypatch, run_id=run_id, files=[CORE], patch_path=CORE
    )
    from agent_shared.bundles.inbox import bundle_dir

    root = bundle_dir(state, run_id=run_id, kind="fix", attempt_id="1", bundle_id=manifest.bundle_id)
    result = run_publish_pdp(
        state_root=state,
        project=PROJECT,
        run_id=run_id,
        bundle_id=manifest.bundle_id,
        bundle_root=root,
        manifest=manifest,
        authorized_files=[CORE],
        source_sha=BASE_SHA,
        agent_branch=f"agent/{run_id}",
        invoked_by="ai-sdlc-lab",
    )
    return state, manifest, result


def test_tb5_source_drift_does_not_publish(tmp_path: Path, monkeypatch) -> None:
    _state, _manifest, result = _pdp_result(tmp_path, monkeypatch, run_id="run-tb5")
    assert result.decision == AUTO_ADMIT
    consumed = witness_and_consume(
        result,
        current_base_sha="ffff000000000000000000000000000000000000",
        patch_digest=result.patch_digest,
        repo=PROJECT,
        target_ref=result.allowed_target_branch,
        policy_digest=result.policy.policy_digest,
    )
    assert consumed["allowed"] is False
    assert consumed["status"] == "SOURCE_DRIFT"


def test_tb6_stale_evidence_does_not_publish(tmp_path: Path, monkeypatch) -> None:
    _state, _manifest, result = _pdp_result(tmp_path, monkeypatch, run_id="run-tb6")
    result.evidence_bundle_digest = "3" * 64
    consumed = witness_and_consume(
        result,
        current_base_sha=BASE_SHA,
        patch_digest=result.patch_digest,
        repo=PROJECT,
        target_ref=result.allowed_target_branch,
        policy_digest=result.policy.policy_digest,
    )
    assert consumed["allowed"] is False
    assert consumed["status"] == "EVIDENCE_STALE"


def test_tb7_wrong_repo_or_branch_does_not_publish(tmp_path: Path, monkeypatch) -> None:
    _state, _manifest, result = _pdp_result(tmp_path, monkeypatch, run_id="run-tb7")
    consumed = witness_and_consume(
        result,
        current_base_sha=BASE_SHA,
        patch_digest=result.patch_digest,
        repo="evil/repo",
        target_ref=result.allowed_target_branch,
        policy_digest=result.policy.policy_digest,
    )
    assert consumed["allowed"] is False
    assert consumed["status"] == "TARGET_MISMATCH"


def test_tb8_required_provider_fail_no_auto_admit(tmp_path: Path, monkeypatch) -> None:
    state, manifest, settings = _seed_publish(
        tmp_path, monkeypatch, run_id="run-tb8", files=[CORE], patch_path=CORE
    )

    def _failing_kwargs(*, envelope, units, **_kwargs):
        return in_process_adapter_kwargs(
            envelope=envelope, units=units, p1_force_failure=True
        )

    with (
        patch("agent_control.publish.pdp.in_process_adapter_kwargs", side_effect=_failing_kwargs),
        patch("agent_control.publish.broker.GiteaClient") as gitea,
        patch("agent_control.publish.broker.push_commit") as push,
    ):
        gitea.return_value.get_branch_sha.return_value = BASE_SHA
        out = broker_publish_fix(
            state_root=state,
            run_id="run-tb8",
            attempt_id="1",
            bundle_id=manifest.bundle_id,
            settings=settings,
        )
    assert out["ok"] is False
    assert out["decision"] != AUTO_ADMIT
    push.assert_not_called()


def test_tb9_forged_actor_evidence_not_authoritative(tmp_path: Path, monkeypatch) -> None:
    state, manifest, _settings_obj = _seed_publish(
        tmp_path, monkeypatch, run_id="run-tb9", files=[CORE], patch_path=CORE
    )
    from agent_shared.bundles.inbox import bundle_dir

    root = bundle_dir(
        state, run_id="run-tb9", kind="fix", attempt_id="1", bundle_id=manifest.bundle_id
    )
    forged = actor_provided_receipt(
        binding={"repo": PROJECT, "source_sha": BASE_SHA, "patch_digest": manifest.patch_sha256}
    )
    real_bus = __import__("agent_control.transaction.evidence.bus", fromlist=["run_evidence_bus"])

    def _bus(**kwargs):
        extra = list(kwargs.get("extra_receipts") or [])
        extra.append(forged)
        kwargs["extra_receipts"] = extra
        return real_bus.run_evidence_bus(**kwargs)

    with patch("agent_control.publish.pdp.run_evidence_bus", side_effect=_bus):
        result = run_publish_pdp(
            state_root=state,
            project=PROJECT,
            run_id="run-tb9",
            bundle_id=manifest.bundle_id,
            bundle_root=root,
            manifest=manifest,
            authorized_files=[CORE],
            source_sha=BASE_SHA,
            agent_branch="agent/run-tb9",
            invoked_by="ai-sdlc-lab",
        )
    forged_items = [
        item
        for item in result.evidence.get("receipts") or []
        if item.get("trust_class") == "ACTOR_PROVIDED"
    ]
    assert forged_items
    assert all(item.get("authoritative") is False for item in forged_items)
    assert all(item.get("can_authorize") is False for item in forged_items)


def test_tb10_policy_digest_change_invalidates_capability(tmp_path: Path, monkeypatch) -> None:
    _state, _manifest, result = _pdp_result(tmp_path, monkeypatch, run_id="run-tb10")
    consumed = witness_and_consume(
        result,
        current_base_sha=BASE_SHA,
        patch_digest=result.patch_digest,
        repo=PROJECT,
        target_ref=result.allowed_target_branch,
        policy_digest="0" * 64,
    )
    assert consumed["allowed"] is False
    assert consumed["status"] == "POLICY_DRIFT"


def test_no_gitea_types_in_c_inputs(tmp_path: Path, monkeypatch) -> None:
    _state, _manifest, result = _pdp_result(tmp_path, monkeypatch, run_id="run-nogitea")
    dumped = json.dumps(result.admission.verification)
    assert "issue_id" not in dumped
    assert "pull_request" not in dumped
    assert "GiteaClient" not in dumped
    assert result.admission.arm == "TRANSACTIONAL_RELATIONAL_ADMISSION"
