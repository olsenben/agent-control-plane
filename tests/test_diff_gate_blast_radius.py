"""Blast-radius consistency in diff gate."""

from agent_shared.closed_world.gate import evaluate_diff_gate
from agent_shared.closed_world.policy import ClosedWorldPolicy
from agent_shared.hash_utils import hash_blast_radius
from agent_shared.models.review import BlastRadiusContext, stub_blast_radius


def _policy() -> ClosedWorldPolicy:
    return ClosedWorldPolicy(policy_sources=["test"])


def test_blast_radius_hash_mismatch() -> None:
    br = BlastRadiusContext(affected_tests=["tests/test_a.py"])
    result = evaluate_diff_gate(
        policy=_policy(),
        unified_diff="",
        changed_files=["src/a.py"],
        allowed_files=["src/a.py"],
        blast_radius=br,
        binding_blast_radius_hash="deadbeef",
    )
    assert any(v.code == "blast_radius_hash_mismatch" for v in result.violations)


def test_ci_hints_drift() -> None:
    br = BlastRadiusContext(affected_tests=["tests/test_a.py"])
    h = hash_blast_radius(br)
    result = evaluate_diff_gate(
        policy=_policy(),
        unified_diff="",
        changed_files=["src/a.py"],
        allowed_files=["src/a.py"],
        fix_ci_hints=["pytest -q", "pytest extra"],
        binding_ci_hints=["pytest -q"],
        blast_radius=br,
        binding_blast_radius_hash=h,
    )
    assert any(v.code == "ci_hints_drift" for v in result.violations)


def test_ci_hints_drift_skipped_when_binding_empty() -> None:
    br = BlastRadiusContext(affected_tests=["tests/test_a.py"])
    h = hash_blast_radius(br)
    result = evaluate_diff_gate(
        policy=_policy(),
        unified_diff="",
        changed_files=["src/a.py"],
        allowed_files=["src/a.py"],
        fix_ci_hints=["pytest -q"],
        binding_ci_hints=[],
        blast_radius=br,
        binding_blast_radius_hash=h,
    )
    assert not any(v.code == "ci_hints_drift" for v in result.violations)


def test_blast_radius_test_drift() -> None:
    br = BlastRadiusContext(affected_tests=["tests/test_a.py"])
    h = hash_blast_radius(br)
    result = evaluate_diff_gate(
        policy=_policy(),
        unified_diff="",
        changed_files=["tests/test_other.py"],
        allowed_files=["tests/test_other.py"],
        blast_radius=br,
        binding_blast_radius_hash=h,
    )
    assert any(v.code == "blast_radius_test_drift" for v in result.violations)


def test_missing_graph_edges_skips_graph_rules() -> None:
    br = stub_blast_radius()
    h = hash_blast_radius(br)
    result = evaluate_diff_gate(
        policy=_policy(),
        unified_diff="",
        changed_files=["tests/test_other.py"],
        allowed_files=["tests/test_other.py"],
        fix_ci_hints=["extra"],
        binding_ci_hints=["pytest -q"],
        blast_radius=br,
        binding_blast_radius_hash=h,
    )
    assert not any(v.code == "blast_radius_test_drift" for v in result.violations)
    assert any(w.code == "graph_incomplete" for w in result.warnings)
