"""Integration: review memory writeback then plan dispatch with prior_memory."""

import json
import os
from pathlib import Path

import pytest

from agent_control.results_ingest import ingest_result_file
from agent_shared.models.events import AgentRunCompletedEvent
from agent_shared.models.intent import CommandIntent
from agent_shared.models.review import ReviewFinding, ReviewResult
from agent_shared.models.state import VerificationState
from agent_control.workflows.dispatch import build_rlm_job
from agent_workers.jobs.rlm_root import process_rlm_root


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
        return dest

    monkeypatch.setattr("agent_workers.flows.runner.clone_repo", _fake_clone)
    return runs


def test_review_then_plan_prior_memory(runs_env: Path) -> None:
    state_root = Path(os.environ["AGENT_STATE_ROOT"])
    review_run_id = "run-review-then-plan"
    review = ReviewResult(
        findings=[ReviewFinding(id="F-001", summary="Add memory retrieval to plan dispatch")],
        files_inspected=["src/agent_control/graph/context_pack.py"],
    )
    inbox = state_root / "inbox" / "ct104-results" / f"{review_run_id}.json"
    inbox.parent.mkdir(parents=True, exist_ok=True)
    event = AgentRunCompletedEvent(
        run_id=review_run_id,
        job_id="j",
        workflow_id=review_run_id,
        session_id=review_run_id,
        trigger_event_id="rtplan",
        project="ai-sdlc-lab/demo-app",
        repo_full_name="ai-sdlc-lab/demo-app",
        flow="code_review",
        agent="reviewer",
        risk_class="read_only_with_repo_context",
        status="completed",
        summary="## Agent Review",
        artifact_root="/tmp",
        command_kind="review",
        issue_id=2,
        review_result=review,
    )
    inbox.write_text(json.dumps(event.model_dump(mode="json")), encoding="utf-8")
    stored, created = ingest_result_file(state_root, inbox)
    assert created is True
    assert stored.exists()

    plan_state = VerificationState(
        project="ai-sdlc-lab/demo-app",
        command_intent=CommandIntent(
            activated=True,
            activation="/agent",
            kind="plan",
            natural_language_task="Plan after review",
            confidence=1.0,
        ),
        dispatch_recommended=True,
    )
    trigger = {
        "event_id": "plan2",
        "delivery_id": "d2",
        "type": "gitea.issue_comment",
        "project": "ai-sdlc-lab/demo-app",
        "payload": {"comment": {"body": "/agent plan", "id": 2}, "issue": {"number": 2}},
    }
    job = build_rlm_job(plan_state, trigger)
    assert job is not None
    assert job.context_pack is not None
    assert "memory_retrieval" in job.context_pack.context_sources
    assert len(job.context_pack.prior_memory) == 1
    assert job.context_pack.prior_memory[0]["run_id"] == review_run_id

    root_result = process_rlm_root(job.model_dump(mode="json"))
    assert root_result["status"] == "completed"
    run_path = Path(root_result["artifact_root"])
    plan_data = json.loads((run_path / "plan_result.json").read_text(encoding="utf-8"))
    assert plan_data.get("prior_memory_used")
    assert plan_data["prior_memory_used"][0]["run_id"] == review_run_id

    context_pack = json.loads((run_path / "context_pack.json").read_text(encoding="utf-8"))
    assert context_pack.get("prior_memory")
