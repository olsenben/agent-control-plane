"""Parse failure terminal reporting tests (Slice 5.1)."""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from agent_control.results_ingest import ingest_result_file
from agent_shared.models.jobs import JobSafety
from agent_workers.flows.runner import run_flow_session
from agent_workers.rlm.fake_engine import FakeRLMEngine
from tests.support.policy_pin import install_fake_policy_pin


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
        "run_id": "run-parse-fail",
        "job_id": "j-parse",
        "workflow_id": "run-parse-fail",
        "session_id": "run-parse-fail",
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
        "proposed_agent_branch": "agent/run-parse-fail",
        "trigger_event_id": "t-parse",
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


def test_parse_failure_reports_inbox_and_ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runs = tmp_path / "runs"
    state = tmp_path / "state"
    runs.mkdir()
    state.mkdir()
    monkeypatch.setenv("AGENT_RUNS_DIR", str(runs))
    monkeypatch.setenv("AGENT_STATE_ROOT", str(state))
    monkeypatch.setenv("AGENT_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("MODEL_ROUTING_POLICY", "fake")
    monkeypatch.setenv("GITEA_AGENT_COMMENT_ENABLED", "true")
    monkeypatch.delenv("GITEA_AGENT_TOKEN", raising=False)
    monkeypatch.delenv("GITEA_BOT_TOKEN", raising=False)
    monkeypatch.setattr("agent_workers.flows.runner.clone_repo", _fake_clone)
    install_fake_policy_pin(monkeypatch)

    def _raise_parse(self, job, workspace, policy, **kwargs):
        artifact_dir = kwargs.get("artifact_dir")
        if artifact_dir:
            parse_path = Path(artifact_dir) / "parse_failure.json"
            parse_path.write_text(
                json.dumps(
                    {
                        "schema_version": "parse_failure.v1",
                        "run_id": job["run_id"],
                        "command_kind": "plan",
                        "parse_errors": ["No JSON object found"],
                    }
                ),
                encoding="utf-8",
            )
        raise ValueError("Failed to parse plan output: no json")

    monkeypatch.setattr(FakeRLMEngine, "run", _raise_parse)

    with patch("agent_workers.gitea_reporter.httpx.post") as mock_post:
        mock_post.return_value.status_code = 201
        mock_post.return_value.json.return_value = {"id": 1}
        with patch("agent_workers.flows.failure_report.enqueue_report", side_effect=Exception("no redis")):
            result = run_flow_session(_plan_job_payload(state))

    assert result["status"] == "failed"
    assert result["terminal_status"] == "failed_parse"
    run_path = Path(result["artifact_root"])
    result_data = json.loads((run_path / "result.json").read_text(encoding="utf-8"))
    assert result_data["terminal_status"] == "failed_parse"

    inbox = state / "inbox" / "ct104-results" / "run-parse-fail.json"
    assert inbox.is_file()
    inbox_payload = json.loads(inbox.read_text(encoding="utf-8"))
    assert inbox_payload["status"] == "failed"
    assert inbox_payload["terminal_status"] == "failed_parse"

    stored, created = ingest_result_file(state, inbox)
    assert created is True
    # V4.1.1: CT104 reporter does not post to Gitea
    assert not mock_post.called
