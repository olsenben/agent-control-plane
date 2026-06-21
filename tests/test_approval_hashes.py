"""Plan and blast-radius hash stability for approvals."""

from agent_shared.hash_utils import hash_plan_result, plan_result_for_hash
from agent_shared.models.plan import PlanResult, PlanStep


def test_plan_hash_excludes_volatile_fields() -> None:
    base = PlanResult(
        scope_summary="scope",
        steps=[PlanStep(id="S1", summary="step", files=["src/a.py"])],
        recommended_next_command="/agent fix WI-0004-abc",
        approval_target_id="WI-0004-abc",
        plan_alias="PLAN-run-abc",
    )
    h1 = hash_plan_result(base)
    mutated = base.model_copy(
        update={
            "recommended_next_command": "/agent fix WI-0004-xyz",
            "approval_target_id": "WI-0004-xyz",
            "plan_alias": "PLAN-run-xyz",
        }
    )
    h2 = hash_plan_result(mutated)
    assert h1 == h2
    assert "approval_target_id" not in plan_result_for_hash(base)
    assert "recommended_next_command" not in plan_result_for_hash(base)
