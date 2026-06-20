"""Tests for plan comment formatter."""

from agent_shared.models.plan import PlanResult, PlanStep
from agent_shared.models.review import BlastRadiusContext
from agent_workers.formatters.plan_comment import render_plan_comment


def test_render_plan_comment_includes_sections() -> None:
    plan = PlanResult(
        scope_summary="Scope text",
        steps=[PlanStep(id="S-001", summary="Do work", files=["src/a.py"])],
        ci_hints=["pytest tests/test_a.py"],
        blast_radius=BlastRadiusContext(
            affected_services=["ct103-control-plane"],
            affected_tests=["tests/test_a.py"],
        ),
        confidence="high",
        recommended_next_command="/agent fix",
    )
    text = render_plan_comment(plan)
    assert "## Agent Plan" in text
    assert "### Steps" in text
    assert "[S-001]" in text
    assert "### CI hints" in text
    assert "ct103-control-plane" in text
    assert "/agent fix" in text
