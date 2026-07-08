"""Semantic output quality gates (Slice 6D.1)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from agent_shared.models.fix import FixResult
from agent_shared.models.plan import PlanResult, PlanStep
from agent_shared.patch_paths import PatchPathError, normalize_repo_relative_path
from agent_workers.gates.runner import APPROVED_PATCH_NAME, collect_changed_files
from agent_workers.rlm.plan_quality import evaluate_plan_quality

_CONTENT_REQUIRED_KINDS = frozenset({"replace", "append", "create"})
_PSEUDO_SOURCES = frozenset(
    {"gitea_issue", "graph_blast_radius", "memory_retrieval", "prior_memory"}
)


@dataclass(frozen=True)
class QualityVerdict:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    stage: str = "quality_gate"


def _step_actionable_text(step: PlanStep) -> str:
    for attr in ("summary", "description", "action", "rationale"):
        value = getattr(step, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def normalize_patch_path(path: str) -> str:
    raw = (path or "").strip().replace("\\", "/")
    if raw.startswith("a/") or raw.startswith("b/"):
        raw = raw[2:]
    if raw.startswith("./"):
        raw = raw[2:]
    return normalize_repo_relative_path(raw)


def evaluate_plan_output_quality(plan: PlanResult) -> QualityVerdict:
    """Require actionable steps with scoped repo files."""
    base = evaluate_plan_quality(plan)
    reasons = list(base.reasons)
    if not plan.steps:
        return QualityVerdict(passed=False, reasons=reasons or ["Plan has no steps."])
    for step in plan.steps:
        if not _step_actionable_text(step):
            reasons.append(f"Plan step {step.id!r} has no actionable text.")
    scoped_files = [
        f.strip()
        for step in plan.steps
        for f in step.files
        if f.strip() and f.strip() not in _PSEUDO_SOURCES
    ]
    if not scoped_files and base.fixable:
        reasons.append("Plan steps do not reference any scoped repository files.")
    passed = base.fixable and not any(
        r.startswith("Plan step") for r in reasons
    )
    return QualityVerdict(passed=passed, reasons=reasons)


def evaluate_fix_output_quality(fix: FixResult) -> QualityVerdict:
    """Require at least one valid file change."""
    reasons: list[str] = []
    if not fix.changes:
        return QualityVerdict(
            passed=False,
            reasons=["Fix has no changes.", "Model returned valid JSON but no file edits."],
        )
    for change in fix.changes:
        path = (change.path or "").strip()
        if not path:
            reasons.append("Fix change missing path.")
            continue
        if change.edit_kind in _CONTENT_REQUIRED_KINDS and not (change.content or "").strip():
            reasons.append(f"Fix change for {path!r} missing content for edit_kind={change.edit_kind!r}.")
    passed = not reasons
    return QualityVerdict(passed=passed, reasons=reasons)


def _diff_parses(unified_diff: str) -> bool:
    text = unified_diff.strip()
    if not text:
        return False
    if "diff --git" in text:
        return True
    return bool(re.search(r"^---\s+", text, re.MULTILINE) and re.search(r"^\+\+\+\s+", text, re.MULTILINE))


def evaluate_patch_artifact(
    artifact_root: Path,
    repo_root: Path,
    allowed_files: list[str] | None = None,
) -> QualityVerdict:
    """Validate promoted patch and working-tree state before publish."""
    reasons: list[str] = []
    patch_path = artifact_root / APPROVED_PATCH_NAME
    if not patch_path.is_file():
        return QualityVerdict(passed=False, reasons=["patch.diff missing."])
    if patch_path.stat().st_size == 0:
        return QualityVerdict(passed=False, reasons=["patch.diff is empty (0 bytes)."])
    unified = patch_path.read_text(encoding="utf-8")
    if not _diff_parses(unified):
        reasons.append("patch.diff is not a valid unified diff.")

    changed = collect_changed_files(repo_root)
    if not changed:
        reasons.append("Working tree has no changed files after apply.")

    if allowed_files:
        try:
            allowed_norm = {normalize_patch_path(p) for p in allowed_files if p.strip()}
        except PatchPathError as exc:
            return QualityVerdict(passed=False, reasons=[str(exc)])
        changed_norm: set[str] = set()
        for path in changed:
            try:
                changed_norm.add(normalize_patch_path(path))
            except PatchPathError:
                reasons.append(f"Changed path failed normalization: {path!r}")
        if allowed_norm and not (changed_norm & allowed_norm):
            reasons.append("No changed files intersect allowed_files scope.")
        extra = sorted(changed_norm - allowed_norm)
        if extra:
            reasons.append(f"Changed files outside allowed scope: {extra}")

    return QualityVerdict(passed=not reasons, reasons=reasons, stage="patch_quality_gate")


def write_quality_gate_result(artifact_root: Path, verdict: QualityVerdict) -> Path:
    path = artifact_root / "quality_gate_result.json"
    payload = {
        "passed": verdict.passed,
        "stage": verdict.stage,
        "reasons": verdict.reasons,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def write_model_output_excerpt(artifact_root: Path, raw: str, *, attempt: int) -> None:
    excerpt_path = artifact_root / f"model_output_excerpt_attempt_{attempt}.json"
    excerpt_path.write_text(
        json.dumps({"attempt": attempt, "excerpt": (raw or "")[:2000]}, indent=2),
        encoding="utf-8",
    )
