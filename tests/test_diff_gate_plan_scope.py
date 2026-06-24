"""Plan scope drift warnings vs hard fail."""

from agent_shared.closed_world.gate import evaluate_diff_gate
from agent_shared.closed_world.policy import ClosedWorldPolicy, PlanScopePolicy
from agent_shared.hash_utils import hash_blast_radius
from agent_shared.models.review import BlastRadiusContext


def test_plan_scope_drift_warning() -> None:
    br = BlastRadiusContext()
    h = hash_blast_radius(br)
    policy = ClosedWorldPolicy(
        plan_scope=PlanScopePolicy(warn_on_drift=True, fail_on_drift=False),
        policy_sources=["test"],
    )
    result = evaluate_diff_gate(
        policy=policy,
        unified_diff="",
        changed_files=["src/extra.py"],
        allowed_files=["src/extra.py"],
        plan_step_files=["src/planned.py"],
        blast_radius=br,
        binding_blast_radius_hash=h,
    )
    assert result.passed
    assert any(w.code == "plan_scope_drift" for w in result.warnings)


def test_plan_scope_drift_hard_fail() -> None:
    br = BlastRadiusContext()
    h = hash_blast_radius(br)
    policy = ClosedWorldPolicy(
        plan_scope=PlanScopePolicy(warn_on_drift=True, fail_on_drift=True),
        policy_sources=["test"],
    )
    result = evaluate_diff_gate(
        policy=policy,
        unified_diff="",
        changed_files=["src/extra.py"],
        allowed_files=["src/extra.py"],
        plan_step_files=["src/planned.py"],
        blast_radius=br,
        binding_blast_radius_hash=h,
    )
    assert not result.passed
    assert any(v.code == "plan_scope_drift" for v in result.violations)
