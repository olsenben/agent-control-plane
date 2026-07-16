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
