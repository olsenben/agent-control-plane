"""Tests for Slice 6F.2 repair gate + sandbox attestation."""

from __future__ import annotations

from pathlib import Path

from agent_control.aci.backends.base import ProbeResult, SandboxAttestation
from agent_control.aci.backends.probes import policy_hash
from agent_control.aci.backends.srt import DenySandboxBackend, get_sandbox_backend
from agent_control.ci.repair import (
    acquire_pr_lock,
    all_required_workflows_terminal,
    consider_repair_dispatch,
    evaluate_repair_allowed,
    release_pr_lock,
    repair_key,
)
from agent_control.config import Settings
from agent_shared.models.ci import (
    CiVerificationResult,
    FailureEvidenceManifest,
    PendingCiRecord,
    RequiredWorkflow,
    WorkflowObservation,
)


def _strong_attestation(ph: str | None = None) -> SandboxAttestation:
    return SandboxAttestation(
        backend="srt",
        backend_version="test",
        mode="strong",
        policy_hash=ph or policy_hash(),
        probes=[ProbeResult(name="canary", passed=True)],
    )


def test_terminal_barrier_blocks_partial_matrix() -> None:
    result = CiVerificationResult(
        fix_run_id="run-1",
        repository="o/r",
        expected_head_commit_sha="abc",
        verdict="failing",
        required_workflows=[
            RequiredWorkflow(path=".gitea/workflows/ci.yaml"),
            RequiredWorkflow(path=".gitea/workflows/lint.yaml"),
        ],
        observations=[
            WorkflowObservation(
                workflow_run_id="1",
                path=".gitea/workflows/ci.yaml",
                head_sha="abc",
                conclusion="failure",
                status="completed",
            ),
        ],
        missing_workflows=[".gitea/workflows/lint.yaml"],
    )
    assert all_required_workflows_terminal(result) is False


def test_repair_allowed_requires_collected_evidence_and_strong_sandbox() -> None:
    settings = Settings(
        FIX_CI_OBSERVE_ENABLED=True,
        FIX_CI_FAILURE_EVIDENCE_ENABLED=True,
        FIX_CI_REPAIR_ENABLED=True,
        SANDBOX_EXPECTED_POLICY_HASH=policy_hash(),
    )
    pending = PendingCiRecord(
        fix_run_id="run-1",
        repository="ai-sdlc-lab/demo-app",
        expected_head_commit_sha="abc",
        opened_pr_number=20,
        agent_branch="agent/fix-1",
        required_workflows=[RequiredWorkflow(path=".gitea/workflows/ci.yaml")],
    )
    result = CiVerificationResult(
        fix_run_id="run-1",
        repository="ai-sdlc-lab/demo-app",
        expected_head_commit_sha="abc",
        verdict="failing",
        required_workflows=pending.required_workflows,
        observations=[
            WorkflowObservation(
                workflow_run_id="1",
                path=".gitea/workflows/ci.yaml",
                head_sha="abc",
                conclusion="failure",
                status="completed",
            ),
        ],
        missing_workflows=[],
    )
    evidence = FailureEvidenceManifest(
        evidence_observation_id="oid",
        status="collected",
        fix_run_id="run-1",
        repository="ai-sdlc-lab/demo-app",
        expected_head_commit_sha="abc",
        workflow_run_id="1",
        failure_class="test_failure",
        has_terminal_failed_job=True,
    )
    gate = evaluate_repair_allowed(
        settings=settings,
        result=result,
        pending=pending,
        evidence=evidence,
        attestation=_strong_attestation(settings.sandbox_expected_policy_hash),
        current_pr_head="abc",
        repair_attempt_count=0,
        branch_ok=True,
        no_unrecognized_commits=True,
    )
    assert gate.allowed is True

    gate2 = evaluate_repair_allowed(
        settings=settings,
        result=result,
        pending=pending,
        evidence=evidence.model_copy(update={"status": "unavailable"}),
        attestation=_strong_attestation(settings.sandbox_expected_policy_hash),
        current_pr_head="abc",
        repair_attempt_count=0,
        branch_ok=True,
        no_unrecognized_commits=True,
    )
    assert gate2.allowed is False
    assert "evidence_not_collected" in gate2.reason_codes
    assert gate2.label == "agent:blocked"


def test_pr_lock_serializes(tmp_path: Path) -> None:
    a = acquire_pr_lock(tmp_path, repository="o/r", pr_number=1, holder="h1")
    assert a is not None
    b = acquire_pr_lock(tmp_path, repository="o/r", pr_number=1, holder="h2")
    assert b is None
    release_pr_lock(a)
    c = acquire_pr_lock(tmp_path, repository="o/r", pr_number=1, holder="h2")
    assert c is not None
    release_pr_lock(c)


def test_consider_dispatch_single_reservation(tmp_path: Path) -> None:
    from unittest.mock import patch

    from support.policy_pin import FAKE_POLICY_PIN

    ph = policy_hash()
    settings = Settings(
        FIX_CI_OBSERVE_ENABLED=True,
        FIX_CI_FAILURE_EVIDENCE_ENABLED=True,
        FIX_CI_REPAIR_ENABLED=True,
        FIX_CI_REPAIR_MAX_ATTEMPTS=1,
        SANDBOX_EXPECTED_POLICY_HASH=ph,
    )
    pending = PendingCiRecord(
        fix_run_id="run-1",
        repository="ai-sdlc-lab/demo-app",
        expected_head_commit_sha="abc",
        opened_pr_number=20,
        agent_branch="agent/fix-1",
        required_workflows=[RequiredWorkflow(path=".gitea/workflows/ci.yaml")],
    )
    result = CiVerificationResult(
        fix_run_id="run-1",
        repository="ai-sdlc-lab/demo-app",
        expected_head_commit_sha="abc",
        verdict="failing",
        required_workflows=pending.required_workflows,
        observations=[
            WorkflowObservation(
                workflow_run_id="1",
                path=".gitea/workflows/ci.yaml",
                head_sha="abc",
                conclusion="failure",
                status="completed",
            ),
        ],
    )
    evidence = FailureEvidenceManifest(
        evidence_observation_id="oid",
        status="collected",
        fix_run_id="run-1",
        repository="ai-sdlc-lab/demo-app",
        expected_head_commit_sha="abc",
        workflow_run_id="1",
        failure_class="lint_failure",
        has_terminal_failed_job=True,
    )
    with patch(
        "agent_control.project_registry.resolve_policy_source_pin",
        return_value=FAKE_POLICY_PIN,
    ):
        d1 = consider_repair_dispatch(
            tmp_path,
            result=result,
            pending=pending,
            evidence=evidence,
            attestation=_strong_attestation(ph),
            current_pr_head="abc",
            settings=settings,
            required_command_ids=["ruff_check"],
        )
    assert d1["dispatched"] is True
    assert d1["repair_attempt"] == 1
    assert d1.get("reservation")
    assert d1["reservation"]["policy_source_sha"] == FAKE_POLICY_PIN.policy_source_sha
    release_pr_lock(Path(d1["lock_path"]))

    # Duplicate observation: reservation exists — no second job
    with patch(
        "agent_control.project_registry.resolve_policy_source_pin",
        return_value=FAKE_POLICY_PIN,
    ):
        d2 = consider_repair_dispatch(
            tmp_path,
            result=result,
            pending=pending,
            evidence=evidence,
            attestation=_strong_attestation(ph),
            current_pr_head="abc",
            settings=settings,
            required_command_ids=["ruff_check"],
        )
    assert d2["dispatched"] is False
    assert "reservation_exists" in d2["reason_codes"]
    if d2.get("lock_path"):
        release_pr_lock(Path(d2["lock_path"]))


def test_deny_backend_never_strong() -> None:
    backend = DenySandboxBackend()
    att = backend.attest(workspace=Path("."), policy_hash=policy_hash())
    assert att.mode == "deny"
    assert att.strong_ok is False


def test_get_sandbox_backend_srt() -> None:
    b = get_sandbox_backend("srt")
    assert b.name == "srt"


def test_repair_key_stable() -> None:
    assert repair_key("o", "r", 20, "sha") == "repair:o/r:20:sha"
