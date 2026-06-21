"""Tests for prior_memory retrieval in context pack."""

from agent_control.graph.context_pack import compile_context_pack, render_context_pack_text
from agent_control.memory.retrieval import STALENESS_REASON_SHA_MISMATCH, apply_staleness
from agent_control.memory.store import MemoryStore
from agent_control.memory.writeback import writeback_from_completed
from agent_shared.models.events import AgentRunCompletedEvent
from agent_shared.models.jobs import TriggerContext
from agent_shared.models.review import ReviewFinding, ReviewResult


def _seed_review_memory(tmp_path, monkeypatch, *, commit_sha: str | None = None) -> str:
    monkeypatch.setenv("AGENT_STATE_ROOT", str(tmp_path))
    run_id = "run-review-seed"
    review = ReviewResult(
        findings=[ReviewFinding(id="F-001", summary="Memory hook missing in dispatch")],
        files_inspected=["src/agent_control/workflows/dispatch.py"],
    )
    event = AgentRunCompletedEvent(
        run_id=run_id,
        job_id="j",
        workflow_id=run_id,
        session_id=run_id,
        trigger_event_id="seed",
        project="ai-sdlc-lab/agent-control-plane",
        repo_full_name="ai-sdlc-lab/agent-control-plane",
        flow="code_review",
        agent="reviewer",
        risk_class="read_only_with_repo_context",
        status="completed",
        summary="review",
        artifact_root="/tmp",
        command_kind="review",
        issue_id=29,
        commit_sha=commit_sha,
        review_result=review,
    )
    writeback_from_completed(event)
    return run_id


def test_compile_context_pack_includes_prior_memory(tmp_path, monkeypatch) -> None:
    run_id = _seed_review_memory(tmp_path, monkeypatch)
    trigger = TriggerContext(event_type="test", issue_number=29)
    pack = compile_context_pack(
        "ai-sdlc-lab/agent-control-plane",
        trigger,
        settings=None,
        command_kind="plan",
        issue_override={"title": "Plan after review", "body": "/agent plan"},
    )
    assert "memory_retrieval" in pack.context_sources
    assert len(pack.prior_memory) == 1
    assert pack.prior_memory[0]["run_id"] == run_id
    assert pack.prior_memory[0]["findings"][0]["id"] == "F-001"

    text = render_context_pack_text(pack)
    assert "--- prior_memory ---" in text
    assert "hypotheses unless marked human_verified" in text
    assert run_id in text


def test_staleness_when_target_sha_differs(tmp_path, monkeypatch) -> None:
    _seed_review_memory(tmp_path, monkeypatch, commit_sha="abc111")
    store = MemoryStore(tmp_path / "memory" / "memory.sqlite")
    record = store.get_latest("ai-sdlc-lab/agent-control-plane", 29)
    assert record is not None
    stale = apply_staleness(record, current_target_sha="def999")
    assert stale.is_stale is True
    assert stale.staleness_reason == STALENESS_REASON_SHA_MISMATCH

    trigger = TriggerContext(event_type="test", issue_number=29)
    from agent_control.config import Settings
    from agent_control.project_registry import RefResolution

    settings = Settings(agent_state_root=tmp_path)
    refs = RefResolution(
        policy_ref="main",
        policy_sha=None,
        task_ref="main",
        task_sha=None,
        base_ref="main",
        target_sha="def999",
        primary_branch="main",
    )
    pack = compile_context_pack(
        "ai-sdlc-lab/agent-control-plane",
        trigger,
        refs=refs,
        settings=settings,
        issue_override={"title": "T", "body": "plan"},
    )
    assert pack.prior_memory[0]["is_stale"] is True
