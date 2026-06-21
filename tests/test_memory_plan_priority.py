"""Tests for plan-prioritized prior_memory retrieval."""

from agent_control.graph.context_pack import compile_context_pack
from agent_control.memory.writeback import writeback_from_completed
from agent_shared.models.events import AgentRunCompletedEvent
from agent_shared.models.jobs import TriggerContext
from agent_shared.models.plan import PlanResult, PlanStep
from agent_shared.models.review import ReviewFinding, ReviewResult


def _seed_plan_memory(tmp_path, monkeypatch, run_id: str, *, steps: int = 5) -> None:
    monkeypatch.setenv("AGENT_STATE_ROOT", str(tmp_path))
    plan = PlanResult(
        scope_summary="Prior plan scope " * 40,
        steps=[
            PlanStep(
                id=f"S-{i:03d}",
                summary=f"Step {i} " * 30,
                files=[f"src/module_{i}.py"],
            )
            for i in range(1, steps + 1)
        ],
        ci_hints=[f"pytest tests/test_{i}.py" for i in range(steps)],
    )
    event = AgentRunCompletedEvent(
        run_id=run_id,
        job_id="j",
        workflow_id=run_id,
        session_id=run_id,
        trigger_event_id=run_id,
        project="ai-sdlc-lab/agent-control-plane",
        repo_full_name="ai-sdlc-lab/agent-control-plane",
        flow="planner",
        agent="planner",
        risk_class="planning_only",
        status="completed",
        summary="plan",
        artifact_root="/tmp",
        command_kind="plan",
        issue_id=29,
        plan_result=plan,
    )
    writeback_from_completed(event)


def _seed_review_memory(tmp_path, monkeypatch, run_id: str) -> None:
    monkeypatch.setenv("AGENT_STATE_ROOT", str(tmp_path))
    review = ReviewResult(
        findings=[ReviewFinding(id="F-001", summary="Review finding for plan priority")],
        files_inspected=["README.md"],
    )
    event = AgentRunCompletedEvent(
        run_id=run_id,
        job_id="j",
        workflow_id=run_id,
        session_id=run_id,
        trigger_event_id=run_id,
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
        review_result=review,
    )
    writeback_from_completed(event)


def test_plan_dispatch_prioritizes_review_over_newer_plan(tmp_path, monkeypatch) -> None:
    _seed_review_memory(tmp_path, monkeypatch, "run-review-old")
    _seed_plan_memory(tmp_path, monkeypatch, "run-plan-new", steps=8)

    from agent_control.config import Settings

    settings = Settings(agent_state_root=tmp_path)
    trigger = TriggerContext(event_type="test", issue_number=29)
    pack = compile_context_pack(
        "ai-sdlc-lab/agent-control-plane",
        trigger,
        settings=settings,
        command_kind="plan",
        issue_override={"title": "Plan", "body": "/agent plan"},
    )

    assert pack.prior_memory
    assert pack.prior_memory[0]["source_command"] == "review"
    assert pack.prior_memory[0]["run_id"] == "run-review-old"
    assert any(m.get("source_command") == "plan" for m in pack.prior_memory[1:])
