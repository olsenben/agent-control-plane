"""CI matrix echo from diff gate."""

from agent_shared.closed_world.gate import evaluate_diff_gate
from agent_shared.closed_world.policy import ClosedWorldPolicy
from agent_shared.hash_utils import hash_blast_radius
from agent_shared.models.review import BlastRadiusContext


def test_ci_matrix_selection() -> None:
    br = BlastRadiusContext(affected_tests=["tests/test_foo.py"])
    h = hash_blast_radius(br)
    result = evaluate_diff_gate(
        policy=ClosedWorldPolicy(policy_sources=["test"]),
        unified_diff="",
        changed_files=["src/a.py"],
        allowed_files=["src/a.py"],
        binding_ci_hints=["pytest -q tests/test_foo.py", ".gitea/workflows/ci.yaml"],
        blast_radius=br,
        binding_blast_radius_hash=h,
    )
    matrix = result.selected_ci_matrix
    assert matrix.dispatch == "deferred_6e"
    assert "pytest -q tests/test_foo.py" in matrix.raw_hints
    assert "plan_ci_hints" in matrix.selection_source
    assert matrix.narrow_tests or matrix.workflows
