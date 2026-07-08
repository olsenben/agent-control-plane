"""Plan output quality gate tests (Slice 6D.1)."""

from agent_shared.models.plan import PlanResult, PlanStep
from agent_workers.rlm.output_quality import evaluate_plan_output_quality


def test_empty_steps_fails_quality_gate() -> None:
    plan = PlanResult(steps=[], fixable=False, quality_gate_reasons=["Plan has no steps."])
    verdict = evaluate_plan_output_quality(plan)
    assert not verdict.passed
    assert any("no steps" in r.lower() for r in verdict.reasons)


def test_good_plan_passes_quality_gate() -> None:
    plan = PlanResult(
        steps=[
            PlanStep(id="S1", summary="Update README with homelab note", files=["README.md"]),
        ],
        fixable=True,
    )
    verdict = evaluate_plan_output_quality(plan)
    assert verdict.passed
    assert verdict.reasons == []


def test_step_without_actionable_text_fails() -> None:
    plan = PlanResult(
        steps=[PlanStep(id="S1", summary="   ", files=["README.md"])],
        fixable=True,
    )
    verdict = evaluate_plan_output_quality(plan)
    assert not verdict.passed
    assert any("actionable" in r.lower() for r in verdict.reasons)
