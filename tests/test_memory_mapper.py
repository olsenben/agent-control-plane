"""Tests for memory_record mapper."""

from agent_control.memory.mapper import memory_record_from_completed
from agent_shared.models.events import AgentRunCompletedEvent
from agent_shared.models.review import BlastRadiusContext, ReviewFinding, ReviewResult


def _review_event(**overrides: object) -> AgentRunCompletedEvent:
    review = ReviewResult(
        findings=[
            ReviewFinding(
                id="F-001",
                summary="Dispatch lacks memory hook",
                file="src/agent_control/workflows/dispatch.py",
                risk_tags=["hallucinated_file_reference"],
            )
        ],
        files_inspected=["src/agent_control/workflows/dispatch.py"],
        blast_radius=BlastRadiusContext(affected_tests=["tests/test_dispatch.py"]),
        risk_tags=["graph_bypass"],
    )
    base = {
        "run_id": "run-review1",
        "job_id": "rlm-root-review1",
        "workflow_id": "run-review1",
        "session_id": "run-review1",
        "trigger_event_id": "review1",
        "project": "ai-sdlc-lab/agent-control-plane",
        "repo_full_name": "ai-sdlc-lab/agent-control-plane",
        "flow": "code_review",
        "agent": "reviewer",
        "risk_class": "read_only_with_repo_context",
        "status": "completed",
        "summary": "## Agent Review",
        "artifact_root": "/mnt/agent-runs/x",
        "command_kind": "review",
        "issue_id": 29,
        "review_result": review,
        "context_sources": ["graph_blast_radius"],
        "engine": "fake_rlm",
        "model_policy": "fake",
    }
    base.update(overrides)
    return AgentRunCompletedEvent.model_validate(base)


def test_mapper_review_produces_record() -> None:
    record = memory_record_from_completed(_review_event())
    assert record is not None
    assert record.repo_full_name == "ai-sdlc-lab/agent-control-plane"
    assert record.repo_owner == "ai-sdlc-lab"
    assert record.issue_id == 29
    assert record.source_command == "review"
    assert record.findings[0].id == "F-001"
    assert "graph_bypass" in record.governance.risk_tags
    assert "hallucinated_file_reference" in record.governance.risk_tags
    assert record.recommended_next_step is not None
    assert record.recommended_next_step.command == "plan"


def test_mapper_inspect_returns_none() -> None:
    event = AgentRunCompletedEvent(
        run_id="run-inspect",
        job_id="j",
        workflow_id="run-inspect",
        session_id="run-inspect",
        trigger_event_id="i1",
        project="ai-sdlc-lab/demo-app",
        flow="inspect",
        agent="explainer",
        risk_class="read_only",
        status="completed",
        summary="ok",
        artifact_root="/tmp/r",
        command_kind="inspect",
    )
    assert memory_record_from_completed(event) is None


def test_mapper_rejects_invalid_repo() -> None:
    assert memory_record_from_completed(
        _review_event(project="not-a-repo", repo_full_name=None)
    ) is None
