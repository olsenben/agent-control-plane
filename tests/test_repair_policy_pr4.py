"""V4.1.1 PR4 — repair allowlist + bounded class + path envelope."""

from __future__ import annotations

import pytest

from agent_control.ci.repair_policy import (
    decide_repair_repository,
    filter_repair_allowed_files,
    intentional_fail_heuristic_allowed,
    normalize_repository,
    parse_repair_allowlist,
    path_prohibited_for_repair,
)
from agent_control.config import Settings


def test_normalize_repository_lower_trim() -> None:
    assert normalize_repository("  AI-SDLC-Lab/Agent-Control-Plane ") == (
        "ai-sdlc-lab/agent-control-plane"
    )


def test_parse_allowlist_rejects_wildcards() -> None:
    with pytest.raises(ValueError, match="wildcards"):
        parse_repair_allowlist("ai-sdlc-lab/*")


def test_parse_allowlist_rejects_invalid() -> None:
    with pytest.raises(ValueError, match="invalid"):
        parse_repair_allowlist("not-a-repo")


def test_empty_allowlist_denies() -> None:
    d = decide_repair_repository(
        "ai-sdlc-lab/agent-control-plane",
        failure_class="lint_failure",
        allowlist_raw="",
    )
    assert not d.allowed
    assert d.reason_code == "repair_allowlist_empty"


def test_non_allowlisted_repo_denied() -> None:
    d = decide_repair_repository(
        "ai-sdlc-lab/demo-app",
        failure_class="lint_failure",
        allowlist_raw="ai-sdlc-lab/agent-control-plane",
    )
    assert not d.allowed
    assert d.reason_code == "repository_not_allowlisted"


def test_acp_lint_allowed_when_listed() -> None:
    d = decide_repair_repository(
        "ai-sdlc-lab/agent-control-plane",
        failure_class="lint_failure",
        allowlist_raw="ai-sdlc-lab/agent-control-plane",
        allowed_classes_raw="lint_failure",
    )
    assert d.allowed
    assert d.matched_allowlist_entry == "ai-sdlc-lab/agent-control-plane"
    assert d.repair_class == "lint_failure"
    assert d.effective_policy_hash


def test_acp_test_failure_denied_by_default_class() -> None:
    d = decide_repair_repository(
        "ai-sdlc-lab/agent-control-plane",
        failure_class="test_failure",
        allowlist_raw="ai-sdlc-lab/agent-control-plane",
        allowed_classes_raw="lint_failure",
    )
    assert not d.allowed
    assert d.reason_code.startswith("failure_class_not_enabled")


def test_publish_requires_publish_flag() -> None:
    d = decide_repair_repository(
        "ai-sdlc-lab/agent-control-plane",
        failure_class="lint_failure",
        allowlist_raw="ai-sdlc-lab/agent-control-plane",
        publish_enabled=False,
        for_publish=True,
    )
    assert not d.allowed
    assert d.reason_code == "repair_publish_disabled"


def test_path_envelope_rejects_trust_paths() -> None:
    assert path_prohibited_for_repair(".agent/policies/tools.yaml")
    assert path_prohibited_for_repair("config/command_registry.yaml")
    assert path_prohibited_for_repair(".gitea/workflows/ci.yaml")
    assert path_prohibited_for_repair("src/agent_control/publish/broker.py")
    assert path_prohibited_for_repair("docker-compose.yml")
    assert path_prohibited_for_repair(".env")
    assert not path_prohibited_for_repair("src/agent_control/ci/comments.py")


def test_filter_repair_allowed_files() -> None:
    kept, rejected = filter_repair_allowed_files(
        [
            "src/foo.py",
            ".agent/x.yml",
            "tests/test_x.py",
        ]
    )
    assert kept == ["src/foo.py", "tests/test_x.py"]
    assert rejected == [".agent/x.yml"]


def test_intentional_fail_heuristic_demo_only() -> None:
    assert intentional_fail_heuristic_allowed("ai-sdlc-lab/demo-app")
    assert not intentional_fail_heuristic_allowed("ai-sdlc-lab/agent-control-plane")


def test_settings_startup_rejects_wildcard_allowlist() -> None:
    with pytest.raises(ValueError, match="wildcards"):
        Settings(
            FIX_CI_OBSERVE_ENABLED=True,
            FIX_CI_FAILURE_EVIDENCE_ENABLED=True,
            FIX_CI_REPAIR_ENABLED=True,
            FIX_CI_REPAIR_ALLOWED_REPOS="ai-sdlc-lab/*",
        )


def test_gate_uses_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_control.aci.backends.base import ProbeResult, SandboxAttestation
    from agent_control.aci.backends.probes import policy_hash
    from agent_control.ci.repair import evaluate_repair_allowed
    from agent_shared.models.ci import (
        CiVerificationResult,
        FailureEvidenceManifest,
        PendingCiRecord,
        RequiredWorkflow,
        WorkflowObservation,
    )

    settings = Settings(
        FIX_CI_OBSERVE_ENABLED=True,
        FIX_CI_FAILURE_EVIDENCE_ENABLED=True,
        FIX_CI_REPAIR_ENABLED=True,
        FIX_CI_REPAIR_ALLOWED_REPOS="ai-sdlc-lab/agent-control-plane",
        FIX_CI_REPAIR_ALLOWED_CLASSES="lint_failure",
        SANDBOX_EXPECTED_POLICY_HASH=policy_hash(),
    )
    pending = PendingCiRecord(
        fix_run_id="run-1",
        repository="ai-sdlc-lab/agent-control-plane",
        expected_head_commit_sha="abc",
        opened_pr_number=1,
        agent_branch="agent/fix-1",
        required_workflows=[RequiredWorkflow(path=".gitea/workflows/ci.yaml")],
    )
    result = CiVerificationResult(
        fix_run_id="run-1",
        repository=pending.repository,
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
        repository=pending.repository,
        expected_head_commit_sha="abc",
        workflow_run_id="1",
        failure_class="lint_failure",
        has_terminal_failed_job=True,
    )
    att = SandboxAttestation(
        backend="srt",
        backend_version="t",
        mode="strong",
        policy_hash=settings.sandbox_expected_policy_hash,
        probes=[ProbeResult(name="c", passed=True)],
    )
    gate = evaluate_repair_allowed(
        settings=settings,
        result=result,
        pending=pending,
        evidence=evidence,
        attestation=att,
        current_pr_head="abc",
        repair_attempt_count=0,
        branch_ok=True,
        no_unrecognized_commits=True,
    )
    assert gate.allowed

    # demo-app still denied even with same class
    pending2 = pending.model_copy(update={"repository": "ai-sdlc-lab/demo-app"})
    evidence2 = evidence.model_copy(update={"repository": "ai-sdlc-lab/demo-app"})
    result2 = result.model_copy(update={"repository": "ai-sdlc-lab/demo-app"})
    gate2 = evaluate_repair_allowed(
        settings=settings,
        result=result2,
        pending=pending2,
        evidence=evidence2,
        attestation=att,
        current_pr_head="abc",
        repair_attempt_count=0,
        branch_ok=True,
        no_unrecognized_commits=True,
    )
    assert not gate2.allowed
    assert "repository_not_allowlisted" in gate2.reason_codes
