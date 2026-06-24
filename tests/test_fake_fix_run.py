"""Fake fix E2E integration test."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from agent_control.approval.dispatch_fix import build_fix_rlm_job
from agent_control.approval.plan_lookup import resolve_plan_for_target
from agent_control.results_ingest import ingest_result_file
from agent_workers.jobs.rlm_root import process_rlm_root
from agent_workers.jobs.report import process_report


@pytest.fixture
def runs_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    runs = tmp_path / "agent-runs"
    state = tmp_path / "agent-state"
    runs.mkdir()
    state.mkdir()
    monkeypatch.setenv("AGENT_RUNS_DIR", str(runs))
    monkeypatch.setenv("AGENT_STATE_ROOT", str(state))
    monkeypatch.setenv("AGENT_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("MODEL_ROUTING_POLICY", "fake")

    def _fake_clone(_settings: object, _repo_url: str, _ref: str, dest: Path) -> Path:
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "README.md").write_text("# Demo\n", encoding="utf-8")
        subprocess.run(["git", "init"], cwd=dest, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=dest, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=dest, check=True, capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=dest, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=dest, check=True, capture_output=True)
        return dest

    monkeypatch.setattr("agent_workers.flows.runner.clone_repo", _fake_clone)
    return runs


def test_fake_fix_end_to_end(runs_env: Path, tmp_path: Path) -> None:
    from conftest import seed_plan_completed
    from agent_control.approval.service import grant_approval

    state_root = tmp_path / "state"
    state_root.mkdir()
    target = seed_plan_completed(state_root)
    approval, _, _ = grant_approval(
        state_root,
        project="ai-sdlc-lab/agent-control-plane",
        issue_id=4,
        target=target,
        approver_login="owner",
        author_is_owner=True,
    )
    assert approval is not None
    record = resolve_plan_for_target(state_root, "ai-sdlc-lab/agent-control-plane", 4, target)
    trigger = {
        "event_id": "fix1",
        "delivery_id": "d-fix",
        "type": "gitea.issue_comment",
        "project": "ai-sdlc-lab/agent-control-plane",
        "payload": {"comment": {"body": f"/agent fix {target}", "id": 1}, "issue": {"number": 4}},
    }
    job = build_fix_rlm_job(
        trigger_event=trigger,
        evaluation_approval=approval,
        plan_record=record,
        fix_run_id="run-fix-fake",
    )
    assert job.fix_authorization is not None
    assert job.command_intent.kind == "fix"

    root_result = process_rlm_root(job.model_dump(mode="json"))
    assert root_result["status"] == "completed"
    run_path = Path(root_result["artifact_root"])
    assert (run_path / "fix_result.json").exists()
    assert (run_path / "patch.diff").exists()
    assert (run_path / "raw_patch.diff").exists()
    assert (run_path / "diff_gate_result.json").exists()

    result_data = json.loads((run_path / "result.json").read_text(encoding="utf-8"))
    assert result_data.get("fix_result") is not None
    assert result_data.get("patch_path") == "patch.diff"

    report_result = process_report(
        {
            "run_id": job.run_id,
            "project": job.project,
            "artifact_root": str(run_path),
            "job": job.model_dump(mode="json"),
            "result": result_data,
        }
    )
    assert report_result["status"] == "reported"
    inbox = Path(os.environ["AGENT_STATE_ROOT"]) / "inbox" / "ct104-results" / f"{job.run_id}.json"
    assert inbox.exists()
    inbox_data = json.loads(inbox.read_text(encoding="utf-8"))
    assert inbox_data.get("command_kind") == "fix"
    assert inbox_data.get("fix_result") is not None

    stored, created = ingest_result_file(Path(os.environ["AGENT_STATE_ROOT"]), inbox)
    assert created is True
    assert stored.exists()
