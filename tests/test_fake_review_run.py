"""Integration test for fake review run."""

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
from support.policy_pin import install_fake_policy_pin


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
        (dest / "README.md").write_text("# Demo\nReview target repo.\n", encoding="utf-8")
        return dest

    monkeypatch.setattr("agent_workers.flows.runner.clone_repo", _fake_clone)
    install_fake_policy_pin(monkeypatch)
    return runs


def test_fake_review_end_to_end(runs_env: Path) -> None:
    state = VerificationState(
        project="ai-sdlc-lab/demo-app",
        command_intent=CommandIntent(
            activated=True,
            activation="/agent",
            kind="review",
            natural_language_task="",
            confidence=1.0,
        ),
        dispatch_recommended=True,
    )
    trigger = {
        "event_id": "review1",
        "delivery_id": "d1",
        "type": "gitea.issue_comment",
        "project": "ai-sdlc-lab/demo-app",
        "payload": {"comment": {"body": "/agent review", "id": 1}, "issue": {"number": 2}},
    }
    job = build_rlm_job(state, trigger)
    assert job is not None
    assert job.flow == "code_review"
    assert job.agent == "reviewer"
    assert job.risk_class == "read_only_with_repo_context"
    assert job.context_pack is not None
    assert "graph_blast_radius" in job.context_pack.context_sources

    root_result = process_rlm_root(job.model_dump(mode="json"))
    assert root_result["status"] == "completed"
    run_path = Path(root_result["artifact_root"])
    required = [
        "bootstrap.json",
        "system_context.json",
        "capabilities.json",
        "metadata.json",
        "policy_source.json",
        "effective_policy.json",
        "context_receipt.json",
        "session_events.jsonl",
        "rlm_trace.jsonl",
        "redaction_report.json",
        "result.json",
        "review_result.json",
    ]
    for name in required:
        assert (run_path / name).exists(), name

    result_data = json.loads((run_path / "result.json").read_text(encoding="utf-8"))
    assert result_data.get("engine") == "fake_rlm"
    assert result_data.get("review_result") is not None
    assert "## Agent Review" in result_data.get("summary", "")
    assert "missing_graph_edges:" in result_data.get("summary", "")
    assert (run_path / "context_pack.json").exists()

    review_data = json.loads((run_path / "review_result.json").read_text(encoding="utf-8"))
    assert review_data.get("schema_version") == "review_result.v1"
    assert review_data.get("recommended_next_command") == "/agent plan"

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
    assert (run_path / "final_report.md").exists()
    inbox = Path(os.environ["AGENT_STATE_ROOT"]) / "inbox" / "ct104-results" / f"{job.run_id}.json"
    assert inbox.exists()
    inbox_data = json.loads(inbox.read_text(encoding="utf-8"))
    assert inbox_data.get("command_kind") == "review"
    assert inbox_data.get("review_result") is not None
    assert inbox_data.get("issue_id") == 2

    stored, created = ingest_result_file(Path(os.environ["AGENT_STATE_ROOT"]), inbox)
    assert created is True
    assert stored.exists()
