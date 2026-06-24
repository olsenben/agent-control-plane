"""Diff gate policy source audit fields."""

from agent_shared.closed_world.gate import evaluate_diff_gate
from agent_shared.closed_world.policy import ClosedWorldPolicy
from agent_shared.hash_utils import hash_blast_radius
from agent_shared.models.review import BlastRadiusContext


def test_policy_sources_recorded() -> None:
    br = BlastRadiusContext()
    policy = ClosedWorldPolicy(
        policy_sources=[".agent/policies/closed_world.yaml", "platform_default/closed_world.yml"],
    )
    result = evaluate_diff_gate(
        policy=policy,
        unified_diff="",
        changed_files=["src/a.py"],
        allowed_files=["src/a.py"],
        approval_id="apr-1",
        approval_target_id="WI-0004-abc",
        plan_run_id="run-abc",
        blast_radius=br,
        binding_blast_radius_hash=hash_blast_radius(br),
    )
    assert result.policy_sources == policy.policy_sources
    assert result.approval_id == "apr-1"
    assert result.recomputed_blast_radius_hash == hash_blast_radius(br)
