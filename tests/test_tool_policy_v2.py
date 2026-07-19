"""Tests for tool_policy.v2 load, fail-closed empty allowance, and hashing."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from agent_control.sandbox import tool_policy as tp
from agent_control.sandbox.command_runner import run_registered_command
from agent_control.config import Settings


@pytest.fixture
def registry() -> dict:
    return {
        "commands": {
            "pytest_narrow": {
                "argv": ["python", "-m", "pytest", "-q"],
                "cwd": "repo_root",
                "timeout_seconds": 120,
                "environment_allowlist": ["PATH"],
                "max_output_bytes": 1024,
            },
            "ruff_check": {
                "argv": ["python", "-m", "ruff", "check", "."],
                "cwd": "repo_root",
                "timeout_seconds": 60,
                "environment_allowlist": ["PATH"],
                "max_output_bytes": 1024,
            },
        },
        "failure_class_commands": {"test_failure": ["pytest_narrow"]},
    }


def test_missing_tools_yaml_empty_allowance(tmp_path: Path, registry: dict) -> None:
    result = tp.load_tool_policy_from_workspace(tmp_path, registry=registry)
    assert result.status == "empty_missing"
    assert result.allowed_command_ids == []
    assert not result.execution_allowed
    assert result.command_registry_hash
    assert result.effective_command_policy_hash


def test_v1_schema_unsupported(registry: dict) -> None:
    text = yaml.dump(
        {
            "schema": "tool_policy.v1",
            "commands": {"pytest_narrow": {"argv": ["pytest"]}},
        }
    )
    result = tp.load_tool_policy_from_text(text, registry=registry)
    assert result.status == "empty_unsupported"
    assert result.allowed_command_ids == []


def test_argv_block_forbidden(registry: dict) -> None:
    text = yaml.dump(
        {
            "schema": "tool_policy.v2",
            "allowed_command_ids": ["pytest_narrow"],
            "commands": {"pytest_narrow": {"argv": ["pytest"]}},
        }
    )
    result = tp.load_tool_policy_from_text(text, registry=registry)
    assert result.status == "empty_invalid"
    assert result.allowed_command_ids == []


def test_unknown_command_id_rejected(registry: dict) -> None:
    text = yaml.dump(
        {
            "schema": "tool_policy.v2",
            "allowed_command_ids": ["pytest_narrow", "mypy"],
            "deny_freeform_shell": True,
            "allow_network": False,
        }
    )
    result = tp.load_tool_policy_from_text(text, registry=registry)
    assert result.status == "empty_invalid"
    assert result.allowed_command_ids == []


def test_unknown_top_level_key_rejected(registry: dict) -> None:
    text = yaml.dump(
        {
            "schema": "tool_policy.v2",
            "allowed_command_ids": ["pytest_narrow"],
            "shell": "bash",
            "deny_freeform_shell": True,
            "allow_network": False,
        }
    )
    result = tp.load_tool_policy_from_text(text, registry=registry)
    assert result.status == "empty_invalid"


def test_allow_network_true_rejected(registry: dict) -> None:
    text = yaml.dump(
        {
            "schema": "tool_policy.v2",
            "allowed_command_ids": ["pytest_narrow"],
            "deny_freeform_shell": True,
            "allow_network": True,
        }
    )
    result = tp.load_tool_policy_from_text(text, registry=registry)
    assert result.status == "empty_invalid"


def test_valid_v2_ok_and_stable_hashes(registry: dict) -> None:
    text = yaml.dump(
        {
            "schema": "tool_policy.v2",
            "allowed_command_ids": ["ruff_check", "pytest_narrow"],
            "constraints": {
                "pytest_narrow": {
                    "allowed_path_globs": ["tests/**"],
                    "max_timeout_seconds": 90,
                }
            },
            "deny_freeform_shell": True,
            "allow_network": False,
        }
    )
    a = tp.load_tool_policy_from_text(text, registry=registry)
    b = tp.load_tool_policy_from_text(text, registry=registry)
    assert a.status == "ok"
    assert a.allowed_command_ids == ["ruff_check", "pytest_narrow"]
    assert a.execution_allowed
    assert a.command_registry_hash == b.command_registry_hash
    assert a.effective_command_policy_hash == b.effective_command_policy_hash
    assert a.hash_algorithm == "sha256"


def test_timeout_may_only_reduce(registry: dict) -> None:
    text = yaml.dump(
        {
            "schema": "tool_policy.v2",
            "allowed_command_ids": ["pytest_narrow"],
            "constraints": {"pytest_narrow": {"max_timeout_seconds": 999}},
            "deny_freeform_shell": True,
            "allow_network": False,
        }
    )
    result = tp.load_tool_policy_from_text(text, registry=registry)
    assert result.status == "empty_invalid"


def test_path_glob_parent_escape_rejected(registry: dict) -> None:
    text = yaml.dump(
        {
            "schema": "tool_policy.v2",
            "allowed_command_ids": ["pytest_narrow"],
            "constraints": {
                "pytest_narrow": {"allowed_path_globs": ["../etc/**"]},
            },
            "deny_freeform_shell": True,
            "allow_network": False,
        }
    )
    result = tp.load_tool_policy_from_text(text, registry=registry)
    assert result.status == "empty_invalid"


def test_intersect_and_runner_deny(tmp_path: Path, registry: dict, registry_file: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    settings = Settings(SANDBOX_BACKEND="deny")
    result = run_registered_command(
        "echo_ok",
        workspace=ws,
        settings=settings,
        registry_path=registry_file,
        allowed_command_ids=[],
    )
    assert result.violated
    assert "tool_policy_rejected" in result.violation_codes


@pytest.fixture
def registry_file(tmp_path: Path) -> Path:
    path = tmp_path / "command_registry.yaml"
    path.write_text(
        """
commands:
  echo_ok:
    argv: ["echo", "hi"]
    cwd: repo_root
    timeout_seconds: 5
    environment_allowlist: ["PATH", "HOME"]
    max_output_bytes: 1024
""",
        encoding="utf-8",
    )
    return path


def test_effective_hash_changes_when_allowlist_changes(registry: dict) -> None:
    a = tp.load_tool_policy_from_text(
        yaml.dump(
            {
                "schema": "tool_policy.v2",
                "allowed_command_ids": ["pytest_narrow"],
                "deny_freeform_shell": True,
                "allow_network": False,
            }
        ),
        registry=registry,
    )
    b = tp.load_tool_policy_from_text(
        yaml.dump(
            {
                "schema": "tool_policy.v2",
                "allowed_command_ids": ["pytest_narrow", "ruff_check"],
                "deny_freeform_shell": True,
                "allow_network": False,
            }
        ),
        registry=registry,
    )
    assert a.command_registry_hash == b.command_registry_hash
    assert a.effective_command_policy_hash != b.effective_command_policy_hash


def test_evaluate_repair_allowed_requires_effective_hash_match() -> None:
    from agent_control.aci.backends.base import ProbeResult, SandboxAttestation
    from agent_control.ci.repair import evaluate_repair_allowed
    from agent_control.config import Settings
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
        FIX_CI_REPAIR_ALLOWED_REPOS="ai-sdlc-lab/demo-app",
        FIX_CI_REPAIR_ALLOWED_CLASSES=(
            "test_failure,lint_failure,build_failure,deterministic_typecheck_failure"
        ),
        SANDBOX_EXPECTED_POLICY_HASH="",
    )
    pending = PendingCiRecord(
        fix_run_id="run-1",
        repository="ai-sdlc-lab/demo-app",
        expected_head_commit_sha="abc",
        opened_pr_number=1,
        agent_branch="agent/x",
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
        fix_run_id="run-1",
        repository="ai-sdlc-lab/demo-app",
        expected_head_commit_sha="abc",
        status="collected",
        failure_class="test_failure",
        has_terminal_failed_job=True,
        evidence_observation_id="obs-1",
        workflow_run_id="1",
    )
    attestation = SandboxAttestation(
        mode="strong",
        policy_hash="x",
        backend="deny",
        backend_version="test",
        probes=[ProbeResult(name="canary", passed=True)],
    )
    gate = evaluate_repair_allowed(
        settings=settings,
        result=result,
        pending=pending,
        evidence=evidence,
        attestation=attestation,
        current_pr_head="abc",
        repair_attempt_count=0,
        branch_ok=True,
        no_unrecognized_commits=True,
        effective_command_policy_hash="hash-a",
        expected_effective_command_policy_hash="hash-b",
        tool_policy_execution_allowed=True,
    )
    assert not gate.allowed
    assert "effective_command_policy_hash_mismatch" in gate.reason_codes
