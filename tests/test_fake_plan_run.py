"""Integration test for fake plan run."""

import json
import os
from pathlib import Path

import pytest

from agent_control.results_ingest import ingest_result_file
from agent_shared.models.intent import CommandIntent
from agent_shared.models.state import VerificationState
from agent_control.workflows.dispatch import build_rlm_job
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
        (dest / "README.md").write_text("# Demo\nPlan target repo.\n", encoding="utf-8")
        return dest

    monkeypatch.setattr("agent_workers.flows.runner.clone_repo", _fake_clone)
    return runs


def test_fake_plan_end_to_end(runs_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_shared.models.context_pack import ContextPack
    from agent_shared.models.review import BlastRadiusContext

    def _fake_context_pack(*_args, **_kwargs) -> ContextPack:
        return ContextPack(
            project="ai-sdlc-lab/demo-app",
            issue_number=2,
            issue_text="# Plan next steps\n\nPlan next steps after review",
            blast_radius=BlastRadiusContext(),
        )

    monkeypatch.setattr(
        "agent_control.workflows.dispatch.compile_context_pack",
        _fake_context_pack,
    )

    state = VerificationState(
        project="ai-sdlc-lab/demo-app",
        command_intent=CommandIntent(
            activated=True,
            activation="/agent",
            kind="plan",
            natural_language_task="",
            confidence=1.0,
        ),
        dispatch_recommended=True,
    )
    trigger = {
        "event_id": "plan1",
        "delivery_id": "d1",
        "type": "gitea.issue_comment",
        "project": "ai-sdlc-lab/demo-app",
        "payload": {"comment": {"body": "/agent plan", "id": 1}, "issue": {"number": 2}},
    }
    job = build_rlm_job(state, trigger)
    assert job is not None
    assert job.flow == "planner"
    assert job.agent == "planner"
    assert job.risk_class == "planning_only"
    assert job.context_pack is not None
    assert job.command_intent.natural_language_task == "Plan next steps after review"

    root_result = process_rlm_root(job.model_dump(mode="json"))
    assert root_result["status"] == "completed"
    run_path = Path(root_result["artifact_root"])
    assert (run_path / "plan_result.json").exists()

    result_data = json.loads((run_path / "result.json").read_text(encoding="utf-8"))
    assert result_data.get("engine") == "fake_rlm"
    assert result_data.get("plan_result") is not None
    assert "## Agent Plan" in result_data.get("summary", "")

    plan_data = json.loads((run_path / "plan_result.json").read_text(encoding="utf-8"))
    assert plan_data.get("schema_version") == "plan_result.v1"
    assert plan_data.get("recommended_next_command", "").startswith("/agent fix WI-")
    assert plan_data.get("approval_target_id")
    assert plan_data.get("plan_alias")

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

    stored, created = ingest_result_file(Path(os.environ["AGENT_STATE_ROOT"]), inbox)
    assert created is True
    assert stored.exists()
