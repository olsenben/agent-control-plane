"""Regression tests for plan finalize quality gate and WI invariant."""

from agent_shared.models.context_pack import ContextPack
from agent_shared.models.plan import PlanResult, PlanStep
from agent_shared.models.review import BlastRadiusContext
from agent_workers.formatters.plan_comment import render_plan_comment
from agent_workers.rlm.plan_finalize import finalize_plan_result


def _job(*, issue_number: int = 16, run_id: str = "run-regression-test") -> dict:
    return {
        "run_id": run_id,
        "trigger_context": {"issue_number": issue_number},
        "context_pack": ContextPack(
            project="ai-sdlc-lab/demo-app",
            issue_number=issue_number,
            blast_radius=BlastRadiusContext(),
        ).model_dump(mode="json"),
    }


def test_empty_steps_no_approval_target_despite_issue() -> None:
    plan = PlanResult(
        scope_summary="empty",
        steps=[],
        risk_tags=["risk-2"],
    )
    _summary, finalized, _warnings = finalize_plan_result(
        plan,
        known_sources=["README.md"],
        job=_job(),
        engine="fake",
    )
    assert finalized.fixable is False
    assert finalized.approval_target_id is None
    assert finalized.plan_alias is None
    assert "WI-" not in finalized.recommended_next_command
    assert "/agent fix" not in finalized.recommended_next_command
    comment = render_plan_comment(finalized)
    assert "Approval required" not in comment
    assert "Plan not fixable" in comment


def test_steps_without_files_no_approval_target() -> None:
    plan = PlanResult(
        scope_summary="Create hello.md",
        steps=[PlanStep(id="S1", summary="Create hello.md", files=[])],
        risk_tags=["risk-2"],
    )
    _summary, finalized, _warnings = finalize_plan_result(
        plan,
        known_sources=["README.md", "hello.md"],
        job=_job(),
        engine="fake",
    )
    assert finalized.fixable is False
    assert finalized.approval_target_id is None
    assert finalized.plan_alias is None
    assert "WI-" not in finalized.recommended_next_command


def test_all_step_files_rejected_no_approval_target() -> None:
    plan = PlanResult(
        scope_summary="bad path",
        steps=[PlanStep(id="S1", summary="edit fake", files=["nonexistent/path.py"])],
        risk_tags=["risk-2"],
    )
    _summary, finalized, warnings = finalize_plan_result(
        plan,
        known_sources=["README.md"],
        job=_job(),
        engine="fake",
    )
    assert any("Rejected hallucinated" in warning for warning in warnings)
    assert finalized.fixable is False
    assert finalized.approval_target_id is None
    assert "path validation" in " ".join(finalized.quality_gate_reasons).lower()


def test_good_plan_with_valid_files_gets_wi_block() -> None:
    plan = PlanResult(
        scope_summary="Update README",
        steps=[PlanStep(id="S1", summary="Update README", files=["README.md"])],
        risk_tags=["risk-2"],
    )
    _summary, finalized, _warnings = finalize_plan_result(
        plan,
        known_sources=["README.md"],
        job=_job(run_id="run-good-plan"),
        engine="fake",
    )
    assert finalized.fixable is True
    assert finalized.approval_target_id is not None
    assert finalized.approval_target_id.startswith("WI-")
    assert finalized.plan_alias is not None
    comment = render_plan_comment(finalized)
    assert "Approval required" in comment
    assert "Plan not fixable" not in comment


def test_workspace_existing_files_pass_without_known_sources(tmp_path) -> None:
    """Stage 3 regression: issue-only context_sources are pseudo tags only."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "demo_app").mkdir()
    (tmp_path / "src" / "demo_app" / "math_service.py").write_text(
        "def add(a, b): return a + b\n", encoding="utf-8"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_math_service.py").write_text(
        "def test_add(): assert True\n", encoding="utf-8"
    )
    plan = PlanResult(
        scope_summary="Add multiply helper",
        steps=[
            PlanStep(
                id="S-001",
                summary="Add multiply to math_service",
                files=["src/demo_app/math_service.py"],
            ),
            PlanStep(
                id="S-002",
                summary="Add test_multiply",
                files=["tests/test_math_service.py"],
            ),
        ],
        risk_tags=["risk-2"],
    )
    _summary, finalized, warnings = finalize_plan_result(
        plan,
        known_sources=["gitea_issue", "graph_blast_radius", "memory_retrieval"],
        job=_job(run_id="run-workspace-plan"),
        engine="official_rlm",
        workspace=tmp_path,
    )
    assert warnings == []
    assert finalized.fixable is True
    assert finalized.approval_target_id is not None
    assert finalized.steps[0].files == ["src/demo_app/math_service.py"]
    assert finalized.steps[1].files == ["tests/test_math_service.py"]