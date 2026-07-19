"""Runner quality-gate propagation and publish guard tests (Slice 6D.1)."""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from agent_shared.constants import TERMINAL_STATUS_FAILED_QUALITY_GATE
from agent_shared.models.fix import FixFileChange, FixResult
from agent_shared.models.jobs import JobSafety
from agent_shared.models.runs import RLMResult
from agent_workers.flows.runner import run_flow_session
from agent_workers.rlm.fake_engine import FakeRLMEngine
from support.policy_pin import install_fake_policy_pin


def _fake_clone(_settings: object, _repo_url: str, _ref: str, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    readme = dest / "README.md"
    if not readme.exists():
        readme.write_text("hi\n", encoding="utf-8")
    if not (dest / ".git").exists():
        subprocess.run(["git", "init"], cwd=dest, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=dest, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=dest, check=True, capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=dest, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=dest, check=True, capture_output=True)
    return dest


def _plan_job_payload(state: Path) -> dict:
    return {
        "run_id": "run-qg-plan",
        "job_id": "j-qg",
        "workflow_id": "run-qg-plan",
        "session_id": "run-qg-plan",
        "workflow_definition": "planner/v1",
        "flow_config_id": "planner",
        "flow_version": "0.1.0",
        "flow_config_schema_version": "v1",
        "project": "ai-sdlc-lab/demo",
        "owner": "ai-sdlc-lab",
        "repo": "demo",
        "repo_url": "http://example/repo",
        "primary_branch": "main",
        "policy_ref": "main",
        "policy_source_repo": "ai-sdlc-lab/demo-app",
        "policy_source_remote": "http://192.168.4.60:3000/ai-sdlc-lab/demo-app",
        "policy_source_ref": "main",
        "policy_source_sha": "0123456789abcdef0123456789abcdef01234567",
        "policy_schema_version": "policy_source.v1",
        "base_ref": "main",
        "target_sha": None,
        "task_ref": "main",
        "proposed_agent_branch": "agent/run-qg-plan",
        "trigger_event_id": "t-qg",
        "trigger_delivery_id": None,
        "trigger_type": "gitea.issue_comment",
        "trigger_context": {
            "source": "gitea",
            "event_type": "gitea.issue_comment",
            "issue_number": 1,
            "author": "owner",
        },
        "flow": "planner",
        "agent": "planner",
        "risk_class": "planning_only",
        "command_intent": {
            "activated": True,
            "activation": "/agent",
            "kind": "plan",
            "natural_language_task": "plan change",
            "confidence": 1.0,
        },
        "reporting": {},
        "limits": {},
        "safety": JobSafety().model_dump(mode="json"),
        "model_policy": "fake",
        "state_path": str(state / "verification_state.json"),
    }


def _fix_job_payload(state: Path) -> dict:
    return {
        "run_id": "run-qg-fix",
        "job_id": "j-qg-fix",
        "workflow_id": "run-qg-fix",
        "session_id": "run-qg-fix",
        "workflow_definition": "developer/v1",
        "flow_config_id": "developer",
        "flow_version": "0.1.0",
        "flow_config_schema_version": "v1",
        "project": "ai-sdlc-lab/demo",
        "owner": "ai-sdlc-lab",
        "repo": "demo",
        "repo_url": "http://example/repo",
        "primary_branch": "main",
        "policy_ref": "main",
        "policy_source_repo": "ai-sdlc-lab/demo-app",
        "policy_source_remote": "http://192.168.4.60:3000/ai-sdlc-lab/demo-app",
        "policy_source_ref": "main",
        "policy_source_sha": "0123456789abcdef0123456789abcdef01234567",
        "policy_schema_version": "policy_source.v1",
        "base_ref": "main",
        "target_sha": None,
        "task_ref": "main",
        "proposed_agent_branch": "agent/run-qg-fix",
        "trigger_event_id": "t-qg-fix",
        "trigger_delivery_id": None,
        "trigger_type": "gitea.issue_comment",
        "trigger_context": {
            "source": "gitea",
            "event_type": "gitea.issue_comment",
            "issue_number": 1,
            "author": "owner",
        },
        "flow": "developer",
        "agent": "developer",
        "risk_class": "write_patch",
        "command_intent": {
            "activated": True,
            "activation": "/agent",
            "kind": "fix",
            "natural_language_task": "WI-0004",
            "confidence": 1.0,
        },
        "reporting": {},
        "limits": {},
        "safety": JobSafety(
            allow_repo_write=True,
            allow_push=True,
            allow_test_execution=False,
        ).model_dump(mode="json"),
        "model_policy": "fake",
        "state_path": str(state / "verification_state.json"),
        "fix_authorization": {
            "approval_id": "appr-1",
            "approval_target_id": "WI-0004",
            "plan_run_id": "run-plan",
            "plan_hash": "abc",
            "blast_radius_hash": "def",
            "allowed_files": ["README.md"],
            "plan_summary": "scope",
            "plan_steps": [],
            "ci_hints": [],
        },
    }


def test_runner_does_not_overwrite_failed_quality_gate_with_completed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs = tmp_path / "runs"
    state = tmp_path / "state"
    runs.mkdir()
    state.mkdir()
    monkeypatch.setenv("AGENT_RUNS_DIR", str(runs))
    monkeypatch.setenv("AGENT_STATE_ROOT", str(state))
    monkeypatch.setenv("AGENT_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("MODEL_ROUTING_POLICY", "fake")
    monkeypatch.setattr("agent_workers.flows.runner.clone_repo", _fake_clone)
    install_fake_policy_pin(monkeypatch)

    def _failed_quality(self, job, workspace, policy, **kwargs):
        return RLMResult(
            run_id=job["run_id"],
            session_id=job["session_id"],
            project=job["project"],
            flow=job["flow"],
            agent=job["agent"],
            risk_class=job["risk_class"],
            workflow_definition=job["workflow_definition"],
            flow_config_id=job["flow_config_id"],
            flow_version=job["flow_version"],
            status="failed",
            terminal_status=TERMINAL_STATUS_FAILED_QUALITY_GATE,
            summary="hollow plan",
            engine="fake_rlm",
        )

    monkeypatch.setattr(FakeRLMEngine, "run", _failed_quality)

    result = run_flow_session(_plan_job_payload(state))
    assert result["status"] == "failed"
    run_path = Path(result["artifact_root"])
    result_data = json.loads((run_path / "result.json").read_text(encoding="utf-8"))
    assert result_data["terminal_status"] == TERMINAL_STATUS_FAILED_QUALITY_GATE
    assert result_data["terminal_status"] != "completed"


def test_empty_patch_never_calls_attempt_remote_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs = tmp_path / "runs"
    state = tmp_path / "state"
    runs.mkdir()
    state.mkdir()
    monkeypatch.setenv("AGENT_RUNS_DIR", str(runs))
    monkeypatch.setenv("AGENT_STATE_ROOT", str(state))
    monkeypatch.setenv("AGENT_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("MODEL_ROUTING_POLICY", "fake")
    monkeypatch.setenv("FIX_REMOTE_PUBLISH_ENABLED", "true")
    monkeypatch.setattr("agent_workers.flows.runner.clone_repo", _fake_clone)
    install_fake_policy_pin(monkeypatch)

    good_fix = FixResult(
        changes=[
            FixFileChange(path="README.md", edit_kind="append", content="line\n"),
        ]
    )

    def _good_fix(self, job, workspace, policy, **kwargs):
        return RLMResult(
            run_id=job["run_id"],
            session_id=job["session_id"],
            project=job["project"],
            flow=job["flow"],
            agent=job["agent"],
            risk_class=job["risk_class"],
            workflow_definition=job["workflow_definition"],
            flow_config_id=job["flow_config_id"],
            flow_version=job["flow_version"],
            status="completed",
            summary="fix ok",
            fix_result=good_fix,
        )

    monkeypatch.setattr(FakeRLMEngine, "run", _good_fix)

    from agent_shared.models.diff_gate import DiffGateResult

    def _gate_pass_no_patch(**_kwargs):
        return DiffGateResult(passed=True)

    monkeypatch.setattr(
        "agent_workers.flows.runner.run_closed_world_diff_gate",
        _gate_pass_no_patch,
    )

    with patch("agent_workers.flows.runner._write_fix_patch_bundle") as mock_bundle:
        result = run_flow_session(_fix_job_payload(state))
        mock_bundle.assert_not_called()

    assert result["status"] == "failed"
    run_path = Path(result["artifact_root"])
    result_data = json.loads((run_path / "result.json").read_text(encoding="utf-8"))
    assert result_data["terminal_status"] == TERMINAL_STATUS_FAILED_QUALITY_GATE
    assert (run_path / "quality_gate_result.json").exists()
