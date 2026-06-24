"""Closed-world diff gate violation cases."""

from agent_shared.closed_world.gate import evaluate_diff_gate
from agent_shared.closed_world.policy import ClosedWorldPolicy, DiffLimits
from agent_shared.hash_utils import hash_blast_radius
from agent_shared.models.review import BlastRadiusContext


def _policy(**kwargs) -> ClosedWorldPolicy:
    base = ClosedWorldPolicy(
        always_denied=["infra/**"],
        requires_elevated_approval=["pyproject.toml"],
        lockfile_globs=["poetry.lock"],
        generated_file_globs=[".agent/state/**"],
        policy_sources=["test"],
    )
    return base.model_copy(update=kwargs)


def _br() -> BlastRadiusContext:
    return BlastRadiusContext(affected_services=["svc"])


def test_denied_path() -> None:
    result = evaluate_diff_gate(
        policy=_policy(),
        unified_diff="--- a/infra/x\n+++ b/infra/x\n",
        changed_files=["infra/x"],
        allowed_files=["infra/x"],
        blast_radius=_br(),
        binding_blast_radius_hash=hash_blast_radius(_br()),
    )
    assert not result.passed
    assert any(v.code == "always_denied_path" for v in result.violations)


def test_elevated_approval_in_allowed_files() -> None:
    result = evaluate_diff_gate(
        policy=_policy(),
        unified_diff="--- a/pyproject.toml\n+++ b/pyproject.toml\n",
        changed_files=["pyproject.toml"],
        allowed_files=["pyproject.toml"],
        blast_radius=_br(),
        binding_blast_radius_hash=hash_blast_radius(_br()),
    )
    assert any(v.code == "elevated_approval_required" for v in result.violations)


def test_diff_size_exceeded() -> None:
    policy = _policy(limits=DiffLimits(max_files_changed=1, max_diff_lines=2))
    result = evaluate_diff_gate(
        policy=policy,
        unified_diff="+a\n+b\n+c\n",
        changed_files=["a.py", "b.py"],
        allowed_files=["a.py", "b.py"],
        blast_radius=_br(),
        binding_blast_radius_hash=hash_blast_radius(_br()),
    )
    assert any(v.code == "diff_size_exceeded" for v in result.violations)


def test_secret_exposure_added_lines() -> None:
    diff = (
        "--- a/src/x.py\n+++ b/src/x.py\n@@\n"
        "+AWS_SECRET_ACCESS_KEY=supersecretvalue123\n"
    )
    result = evaluate_diff_gate(
        policy=_policy(),
        unified_diff=diff,
        changed_files=["src/x.py"],
        allowed_files=["src/x.py"],
        blast_radius=_br(),
        binding_blast_radius_hash=hash_blast_radius(_br()),
    )
    assert any(v.code == "secret_exposure" for v in result.violations)


def test_lockfile_edit() -> None:
    result = evaluate_diff_gate(
        policy=_policy(),
        unified_diff="--- a/poetry.lock\n+++ b/poetry.lock\n",
        changed_files=["poetry.lock"],
        allowed_files=["poetry.lock"],
        blast_radius=_br(),
        binding_blast_radius_hash=hash_blast_radius(_br()),
    )
    assert any(v.code == "lockfile_edit" for v in result.violations)


def test_generated_state_edit() -> None:
    result = evaluate_diff_gate(
        policy=_policy(),
        unified_diff="--- a/.agent/state/foo.json\n+++ b/.agent/state/foo.json\n",
        changed_files=[".agent/state/foo.json"],
        allowed_files=[".agent/state/foo.json"],
        blast_radius=_br(),
        binding_blast_radius_hash=hash_blast_radius(_br()),
    )
    assert any(v.code == "generated_state_edit" for v in result.violations)


def test_test_weakening_detected() -> None:
    diff = (
        "--- a/tests/test_foo.py\n+++ b/tests/test_foo.py\n"
        "@@\n-def test_bar():\n-    assert True\n"
    )
    result = evaluate_diff_gate(
        policy=_policy(),
        unified_diff=diff,
        changed_files=["tests/test_foo.py"],
        allowed_files=["tests/test_foo.py"],
        blast_radius=_br(),
        binding_blast_radius_hash=hash_blast_radius(_br()),
    )
    assert any(v.code == "test_weakening_detected" for v in result.violations)


def test_out_of_scope_path() -> None:
    result = evaluate_diff_gate(
        policy=_policy(),
        unified_diff="",
        changed_files=["src/other.py"],
        allowed_files=["src/allowed.py"],
        blast_radius=_br(),
        binding_blast_radius_hash=hash_blast_radius(_br()),
    )
    assert any(v.code == "out_of_scope_path" for v in result.violations)


def test_collects_multiple_violations() -> None:
    result = evaluate_diff_gate(
        policy=_policy(),
        unified_diff="+AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n",
        changed_files=["pyproject.toml", "infra/x"],
        allowed_files=["pyproject.toml", "infra/x"],
        blast_radius=_br(),
        binding_blast_radius_hash=hash_blast_radius(_br()),
    )
    codes = result.violation_codes()
    assert "elevated_approval_required" in codes
    assert "always_denied_path" in codes
