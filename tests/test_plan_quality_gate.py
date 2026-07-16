"""Unit tests for plan quality gate."""

from agent_shared.models.plan import PlanResult, PlanStep
from agent_workers.rlm.plan_quality import REPLAN_HINT, evaluate_plan_quality


def test_empty_steps_not_fixable() -> None:
    plan = PlanResult(scope_summary="empty", steps=[])
    result = evaluate_plan_quality(plan)
    assert result.fixable is False
    assert "Plan has no steps." in result.reasons
    assert REPLAN_HINT in result.reasons


def test_steps_without_files_not_fixable() -> None:
    plan = PlanResult(
        scope_summary="workflow prose only",
        steps=[PlanStep(id="S1", summary="Create hello.md", files=[])],
    )
    result = evaluate_plan_quality(plan)
    assert result.fixable is False
    assert "Plan steps do not reference any valid repository files." in result.reasons


def test_all_paths_rejected_not_fixable() -> None:
    plan = PlanResult(
        scope_summary="bad paths",
        steps=[PlanStep(id="S1", summary="edit", files=[])],
    )
    warnings = ["Rejected hallucinated step file paths: fake/path.py"]
    result = evaluate_plan_quality(plan, path_validation_warnings=warnings)
    assert result.fixable is False
    assert "Plan referenced files, but none passed repository path validation." in result.reasons


def test_good_plan_with_files_is_fixable() -> None:
    plan = PlanResult(
        scope_summary="hello",
        steps=[PlanStep(id="S1", summary="Create hello.md", files=["hello.md"])],
    )
    result = evaluate_plan_quality(plan)
    assert result.fixable is True
    assert result.reasons == []


def test_fake_engine_shaped_plan_is_fixable() -> None:
    plan = PlanResult(
        scope_summary="readme",
        steps=[PlanStep(id="S1", summary="Update README", files=["README.md"])],
    )
    result = evaluate_plan_quality(plan)
    assert result.fixable is True
