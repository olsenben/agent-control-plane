"""Deterministic closed-world diff gate evaluation (Slice 6C)."""

from __future__ import annotations

import re
from typing import Any

from agent_shared.closed_world.policy import ClosedWorldPolicy, any_glob_match, paths_matching_any
from agent_shared.closed_world.secrets import scan_added_lines_for_secrets
from agent_shared.hash_utils import hash_blast_radius
from agent_shared.models.diff_gate import (
    CiMatrixSelection,
    DiffGateResult,
    DiffGateViolation,
    DiffGateWarning,
)
from agent_shared.models.review import BlastRadiusContext, stub_blast_radius
from agent_shared.patch_paths import normalize_repo_relative_path


def _normalize_files(files: list[str]) -> list[str]:
    out: list[str] = []
    for f in files:
        try:
            out.append(normalize_repo_relative_path(f))
        except ValueError:
            out.append(f.strip().replace("\\", "/"))
    return sorted(set(out))


def _count_diff_lines(unified_diff: str) -> int:
    count = 0
    for line in unified_diff.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            count += 1
        elif line.startswith("-") and not line.startswith("---"):
            count += 1
    return count


def _extract_added_lines(unified_diff: str) -> list[str]:
    added: list[str] = []
    for line in unified_diff.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            added.append(line[1:])
    return added


def _extract_deleted_test_signals(unified_diff: str, changed_files: list[str]) -> list[str]:
    signals: list[str] = []
    for path in changed_files:
        base = path.split("/")[-1]
        if path.startswith("tests/") or base.startswith("test_") or base.endswith("_test.py"):
            if path not in _files_with_only_additions(unified_diff):
                signals.append(f"test file modified: {path}")
    return signals


def _files_with_only_additions(unified_diff: str) -> set[str]:
    """Files that appear only as new files (simplified)."""
    current: str | None = None
    has_removal = set()
    for line in unified_diff.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:].strip()
        elif current and line.startswith("-") and not line.startswith("---"):
            has_removal.add(current)
    return set()


def _detect_deleted_test_files(
    unified_diff: str,
    changed_files: list[str],
    policy: ClosedWorldPolicy,
) -> list[str]:
    if not policy.test_deletion.flag_deleted_test_files:
        return []
    deleted: list[str] = []
    current: str | None = None
    file_has_add = False
    file_has_del = False
    for line in unified_diff.splitlines():
        if line.startswith("+++ b/"):
            if current and _is_test_path(current) and file_has_del and not file_has_add:
                deleted.append(current)
            current = line[6:].strip()
            file_has_add = False
            file_has_del = False
        elif line.startswith("+") and not line.startswith("+++"):
            file_has_add = True
        elif line.startswith("-") and not line.startswith("---"):
            file_has_del = True
    if current and _is_test_path(current) and file_has_del and not file_has_add:
        deleted.append(current)
    for path in changed_files:
        if _is_test_path(path) and path not in deleted:
            pass
    return deleted


def _is_test_path(path: str) -> bool:
    base = path.split("/")[-1]
    return path.startswith("tests/") or base.startswith("test_") or base.endswith("_test.py")


def _detect_assertion_removals(unified_diff: str, policy: ClosedWorldPolicy) -> list[str]:
    if not policy.test_deletion.flag_assertion_removals:
        return []
    hits: list[str] = []
    current: str | None = None
    for line in unified_diff.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:].strip()
        elif current and _is_test_path(current) and line.startswith("-") and not line.startswith("---"):
            body = line[1:].strip()
            if re.search(r"\bassert\b", body) or "pytest.raises" in body or re.match(r"def test_", body):
                hits.append(f"{current}: removed {body[:60]}")
    return hits


def _graph_has_data(br: BlastRadiusContext) -> bool:
    if br.missing_graph_edges and not (
        br.affected_repos or br.affected_services or br.affected_tests or br.related_adrs
    ):
        return False
    return bool(
        br.affected_repos or br.affected_services or br.affected_tests or br.related_adrs
    )


def _build_ci_matrix(
    ci_hints: list[str],
    blast_radius: BlastRadiusContext,
) -> CiMatrixSelection:
    narrow_tests: list[str] = []
    workflows: list[str] = []
    sources: list[str] = []
    raw = list(ci_hints)

    if ci_hints:
        sources.append("plan_ci_hints")
    for hint in ci_hints:
        h = hint.strip()
        if ".gitea/workflows/" in h or h.endswith(".yaml") or h.endswith(".yml"):
            workflows.append(h)
            if "workflow_policy" not in sources:
                sources.append("workflow_policy")
        elif h.startswith("pytest") or h.startswith("tests/") or "/test_" in h:
            narrow_tests.append(h)
            if "affected_tests" not in sources:
                sources.append("affected_tests")

    for test in blast_radius.affected_tests:
        if test not in narrow_tests:
            narrow_tests.append(test)
        if "affected_tests" not in sources:
            sources.append("affected_tests")

    return CiMatrixSelection(
        narrow_tests=narrow_tests,
        workflows=workflows,
        raw_hints=raw,
        selection_source=sources or ["plan_ci_hints"],
        dispatch="deferred_6e",
    )


def evaluate_diff_gate(
    *,
    policy: ClosedWorldPolicy,
    unified_diff: str,
    changed_files: list[str],
    allowed_files: list[str],
    fix_ci_hints: list[str] | None = None,
    binding_ci_hints: list[str] | None = None,
    blast_radius: BlastRadiusContext | None = None,
    binding_blast_radius_hash: str | None = None,
    plan_step_files: list[str] | None = None,
    approval_id: str | None = None,
    approval_target_id: str | None = None,
    plan_run_id: str | None = None,
) -> DiffGateResult:
    """Pure policy evaluation; collects all violations and warnings."""
    changed = _normalize_files(changed_files)
    allowed = _normalize_files(allowed_files)
    allowed_set = set(allowed)
    violations: list[DiffGateViolation] = []
    warnings: list[DiffGateWarning] = []

    br = blast_radius or stub_blast_radius()
    recomputed_hash = hash_blast_radius(br)

    # 1. Diff size limits
    if len(changed) > policy.limits.max_files_changed:
        violations.append(
            DiffGateViolation(
                code="diff_size_exceeded",
                message=f"changed file count {len(changed)} exceeds max {policy.limits.max_files_changed}",
            )
        )
    diff_lines = _count_diff_lines(unified_diff)
    if diff_lines > policy.limits.max_diff_lines:
        violations.append(
            DiffGateViolation(
                code="diff_size_exceeded",
                message=f"diff line count {diff_lines} exceeds max {policy.limits.max_diff_lines}",
            )
        )

    # 2. Always denied
    for path in paths_matching_any(changed, policy.always_denied):
        violations.append(
            DiffGateViolation(
                code="always_denied_path",
                path=path,
                message=f"path matches always_denied policy: {path!r}",
            )
        )

    # 3. Elevated approval required
    for path in paths_matching_any(changed, policy.requires_elevated_approval):
        violations.append(
            DiffGateViolation(
                code="elevated_approval_required",
                path=path,
                message=(
                    "Risk 2 approval does not authorize dependency manifests, workflows, "
                    f"lockfiles, ADRs, or generated state: {path!r}"
                ),
            )
        )

    # 4. Out of scope
    for path in changed:
        if path not in allowed_set:
            violations.append(
                DiffGateViolation(
                    code="out_of_scope_path",
                    path=path,
                    message=f"path not in allowed_files: {path!r}",
                )
            )

    # 5. Lockfiles
    for path in paths_matching_any(changed, policy.lockfile_globs):
        violations.append(
            DiffGateViolation(
                code="lockfile_edit",
                path=path,
                message=f"lockfile or dependency manifest edit blocked: {path!r}",
            )
        )

    # 6. Generated state
    for path in paths_matching_any(changed, policy.generated_file_globs):
        violations.append(
            DiffGateViolation(
                code="generated_state_edit",
                path=path,
                message=f"generated state file edit blocked: {path!r}",
            )
        )

    # 7. Secret scan (added lines only)
    if policy.secret_scan.enabled:
        added_lines = _extract_added_lines(unified_diff)
        secret_hits = scan_added_lines_for_secrets(added_lines)
        for label in secret_hits:
            violations.append(
                DiffGateViolation(
                    code="secret_exposure",
                    message=f"secret pattern detected in added lines: {label}",
                )
            )

    # 8. Test weakening
    deleted_tests = _detect_deleted_test_files(unified_diff, changed, policy)
    for path in deleted_tests:
        violations.append(
            DiffGateViolation(
                code="test_weakening_detected",
                path=path,
                message=(
                    "Blocked because this patch appears to delete or weaken tests. "
                    "Re-plan with explicit test-change approval."
                ),
            )
        )
    for hit in _detect_assertion_removals(unified_diff, policy):
        violations.append(
            DiffGateViolation(
                code="test_weakening_detected",
                message=hit,
            )
        )

    # 9. Blast-radius consistency
    if binding_blast_radius_hash and recomputed_hash != binding_blast_radius_hash:
        violations.append(
            DiffGateViolation(
                code="blast_radius_hash_mismatch",
                message="context_pack blast_radius hash does not match approval binding",
            )
        )

    graph_ok = _graph_has_data(br)
    if not graph_ok and br.missing_graph_edges:
        warnings.append(
            DiffGateWarning(
                code="graph_incomplete",
                message="graph blast-radius incomplete; skipping graph-specific drift checks",
            )
        )

    if graph_ok and br.affected_tests:
        changed_tests = [p for p in changed if _is_test_path(p)]
        if changed_tests:
            allowed_tests = set(br.affected_tests)
            drift = [p for p in changed_tests if p not in allowed_tests]
            for path in drift:
                violations.append(
                    DiffGateViolation(
                        code="blast_radius_test_drift",
                        path=path,
                        message=f"changed test not in blast_radius.affected_tests: {path!r}",
                    )
                )

    if graph_ok and binding_ci_hints:
        if fix_ci_hints is not None:
            binding_set = {h.strip() for h in binding_ci_hints if h.strip()}
            extra = [h for h in fix_ci_hints if h.strip() and h.strip() not in binding_set]
            for hint in extra:
                violations.append(
                    DiffGateViolation(
                        code="ci_hints_drift",
                        message=f"fix ci_hint not in approved binding: {hint!r}",
                    )
                )

    if graph_ok and br.related_adrs:
        for path in changed:
            for adr in br.related_adrs:
                if adr in path or path.startswith("docs/adr/"):
                    if path not in allowed_set:
                        violations.append(
                            DiffGateViolation(
                                code="blast_radius_adr_drift",
                                path=path,
                                message=f"ADR-related path change outside allowed_files: {path!r}",
                            )
                        )

    # 10. Plan scope drift
    if plan_step_files is not None:
        plan_files = _normalize_files(plan_step_files)
        plan_set = set(plan_files)
        drift_paths = [p for p in changed if p in allowed_set and p not in plan_set]
        if drift_paths:
            msg = f"changed files not in approved plan steps: {drift_paths}"
            if policy.plan_scope.fail_on_drift:
                violations.append(
                    DiffGateViolation(code="plan_scope_drift", message=msg)
                )
            elif policy.plan_scope.warn_on_drift:
                warnings.append(
                    DiffGateWarning(code="plan_scope_drift", paths=drift_paths, message=msg)
                )

    # 11. CI matrix echo
    ci_matrix = _build_ci_matrix(binding_ci_hints or fix_ci_hints or [], br)

    passed = len(violations) == 0
    return DiffGateResult(
        passed=passed,
        policy_version=policy.schema_version,
        policy_sources=list(policy.policy_sources),
        approval_id=approval_id,
        approval_target_id=approval_target_id,
        plan_run_id=plan_run_id,
        blast_radius_hash=binding_blast_radius_hash,
        recomputed_blast_radius_hash=recomputed_hash,
        allowed_files=allowed,
        changed_files=changed,
        violations=violations,
        warnings=warnings,
        selected_ci_matrix=ci_matrix,
    )
