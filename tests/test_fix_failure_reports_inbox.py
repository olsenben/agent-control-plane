"""Fix failure reporting and no-push guard tests."""

import json
import subprocess
from pathlib import Path

import pytest

from agent_shared.models.fix import FixFileChange, FixResult
from agent_shared.models.jobs import JobSafety
from agent_workers.flows.runner import run_flow_session
from agent_workers.jobs.report import process_report
from agent_workers.rlm.fake_engine import FakeRLMEngine
from support.policy_pin import install_fake_policy_pin


def test_fix_no_push_guard_in_safety_and_dispatch() -> None:
    from agent_control.approval.dispatch_fix import _safety_for_fix

    safety = _safety_for_fix()
    assert safety.allow_push is False
    assert safety.allow_merge is False


def test_no_gitea_pr_client_on_fix_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("AGENT_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("AGENT_CACHE_DIR", str(tmp_path / "cache"))

    from agent_workers.gitea_reporter import maybe_post_comment
    from agent_shared.models.events import AgentRunCompletedEvent

    completed = AgentRunCompletedEvent(
        run_id="run-x",
        job_id="j1",
        workflow_id="run-x",
        session_id="run-x",
        trigger_event_id="t1",
        project="ai-sdlc-lab/demo",
        flow="developer",
        agent="developer",
        risk_class="write_patch",
        status="failed",
        summary="fix failed",
        artifact_root="/tmp",
        command_kind="fix",
    )
    out = maybe_post_comment(
        type(
            "S",
            (),
            {
                "gitea_agent_comment_enabled": True,
                "gitea_agent_token": "tok",
                "gitea_base_url": "http://g",
            },
        )(),
        {"trigger_context": {"issue_number": 1, "author": "u"}},
        completed,
        tmp_path,
    )
    # V4.1.1: CT104 never posts comments
    assert out["status"] == "skipped"
    assert "ct103" in out.get("reason", "")


def test_apply_failure_still_reports_inbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runs = tmp_path / "runs"
    state = tmp_path / "state"
    runs.mkdir()
    state.mkdir()
    monkeypatch.setenv("AGENT_RUNS_DIR", str(runs))
    monkeypatch.setenv("AGENT_STATE_ROOT", str(state))
    monkeypatch.setenv("AGENT_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("MODEL_ROUTING_POLICY", "fake")

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

    monkeypatch.setattr("agent_workers.flows.runner.clone_repo", _fake_clone)
    install_fake_policy_pin(monkeypatch)

    bad_fix = FixResult(
        changes=[
            FixFileChange(path="not-in-allowlist.py", edit_kind="create", content="x\n"),
        ]
    )

    def _broken_fix(self, job, workspace, policy, **kwargs):
        from agent_shared.models.runs import RLMResult

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
            summary="will fail apply",
            fix_result=bad_fix,
        )

    monkeypatch.setattr(FakeRLMEngine, "run", _broken_fix)

    job_payload = {
        "run_id": "run-fail-fix",
        "job_id": "j-fail",
        "workflow_id": "run-fail-fix",
        "session_id": "run-fail-fix",
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
        "proposed_agent_branch": "agent/run-fail-fix",
        "trigger_event_id": "t-fail",
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
            allow_push=False,
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

    result = run_flow_session(job_payload)
    assert result["status"] == "failed"
    run_path = Path(result["artifact_root"])
    assert (run_path / "error.json").exists()

    result_data = json.loads((run_path / "result.json").read_text(encoding="utf-8"))
    assert result_data["status"] == "failed"

    report = process_report(
        {
            "run_id": "run-fail-fix",
            "project": "ai-sdlc-lab/demo",
            "artifact_root": str(run_path),
            "job": job_payload,
            "result": result_data,
        }
    )
    inbox = state / "inbox" / "ct104-results" / "run-fail-fix.json"
    assert inbox.exists()
    assert report["status"] == "reported"


def test_gate_failure_reports_inbox_with_deny(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runs = tmp_path / "runs"
    state = tmp_path / "state"
    runs.mkdir()
    state.mkdir()
    monkeypatch.setenv("AGENT_RUNS_DIR", str(runs))
    monkeypatch.setenv("AGENT_STATE_ROOT", str(state))
    monkeypatch.setenv("AGENT_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("MODEL_ROUTING_POLICY", "fake")

    def _fake_clone(_settings: object, _repo_url: str, _ref: str, dest: Path) -> Path:
        dest.mkdir(parents=True, exist_ok=True)
        readme = dest / "README.md"
        readme.write_text("hi\n", encoding="utf-8")
        subprocess.run(["git", "init"], cwd=dest, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=dest, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=dest, check=True, capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=dest, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=dest, check=True, capture_output=True)
        return dest

    monkeypatch.setattr("agent_workers.flows.runner.clone_repo", _fake_clone)
    install_fake_policy_pin(monkeypatch)

    secret_fix = FixResult(
        changes=[
            FixFileChange(
                path="README.md",
                edit_kind="replace",
                content="hi\nAWS_SECRET_ACCESS_KEY=leaked\n",
            )
        ]
    )

    def _secret_fix(self, job, workspace, policy, **kwargs):
        from agent_shared.models.runs import RLMResult

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
            summary="will fail gate",
            fix_result=secret_fix,
        )

    monkeypatch.setattr(FakeRLMEngine, "run", _secret_fix)

    from agent_shared.hash_utils import hash_blast_radius
    from agent_shared.models.review import BlastRadiusContext

    br = BlastRadiusContext(affected_services=["svc"])
    blast_hash = hash_blast_radius(br)

    job_payload = {
        "run_id": "run-gate-fail",
        "job_id": "j-gate",
        "workflow_id": "run-gate-fail",
        "session_id": "run-gate-fail",
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
        "proposed_agent_branch": "agent/run-gate-fail",
        "trigger_event_id": "t-gate",
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
            allow_push=False,
            allow_test_execution=False,
        ).model_dump(mode="json"),
        "model_policy": "fake",
        "state_path": str(state / "verification_state.json"),
        "context_pack": {
            "project": "ai-sdlc-lab/demo",
            "blast_radius": br.model_dump(mode="json"),
        },
        "fix_authorization": {
            "approval_id": "appr-1",
            "approval_target_id": "WI-0004",
            "plan_run_id": "run-plan",
            "plan_hash": "abc",
            "blast_radius_hash": blast_hash,
            "allowed_files": ["README.md"],
            "plan_summary": "scope",
            "plan_steps": [{"id": "S1", "files": ["README.md"]}],
            "ci_hints": ["pytest -q"],
        },
    }

    result = run_flow_session(job_payload)
    assert result["status"] == "failed"
    run_path = Path(result["artifact_root"])
    assert (run_path / "raw_patch.diff").exists()
    assert not (run_path / "patch.diff").exists()
    assert (run_path / "diff_gate_result.json").exists()

    result_data = json.loads((run_path / "result.json").read_text(encoding="utf-8"))
    process_report(
        {
            "run_id": "run-gate-fail",
            "project": "ai-sdlc-lab/demo",
            "artifact_root": str(run_path),
            "job": job_payload,
            "result": result_data,
        }
    )
    inbox = state / "inbox" / "ct104-results" / "run-gate-fail.json"
    assert inbox.exists()
    payload = json.loads(inbox.read_text(encoding="utf-8"))
    assert payload["policy_decision"] == "deny"
    assert payload["diff_gate_passed"] is False
    assert "secret_exposure" in payload.get("diff_gate_violation_codes", [])
