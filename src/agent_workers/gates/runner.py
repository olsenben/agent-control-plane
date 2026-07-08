"""Closed-world diff gate runner (CT104 I/O wrapper)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from agent_shared.closed_world.gate import evaluate_diff_gate
from agent_shared.closed_world.loader import load_closed_world_policy
from agent_shared.models.context_pack import ContextPack
from agent_shared.models.diff_gate import DiffGateResult
from agent_shared.models.review import BlastRadiusContext


class DiffGateError(Exception):
    """Raised when diff gate fails."""

    def __init__(self, result: DiffGateResult):
        self.result = result
        codes = ", ".join(result.violation_codes()) or "unknown"
        super().__init__(f"diff gate failed: {codes}")


RAW_PATCH_NAME = "raw_patch.diff"
APPROVED_PATCH_NAME = "patch.diff"


def collect_changed_files(repo_root: Path) -> list[str]:
    tracked = _git_lines(repo_root, ["git", "diff", "--name-only"])
    untracked = _git_lines(
        repo_root,
        ["git", "ls-files", "--others", "--exclude-standard"],
    )
    return sorted(set(tracked) | set(untracked))


def read_unified_diff(repo_root: Path) -> str:
    proc = subprocess.run(
        ["git", "diff"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return ""
    untracked = _git_lines(
        repo_root,
        ["git", "ls-files", "--others", "--exclude-standard"],
    )
    parts = [proc.stdout]
    for path in untracked:
        null_dev = "NUL" if os.name == "nt" else "/dev/null"
        show = subprocess.run(
            ["git", "diff", "--no-index", null_dev, path],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if show.stdout:
            parts.append(show.stdout)
    return "\n".join(p for p in parts if p)


def _git_lines(repo_root: Path, cmd: list[str]) -> list[str]:
    proc = subprocess.run(
        cmd,
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _plan_step_files(binding: dict[str, Any]) -> list[str]:
    files: list[str] = []
    for step in binding.get("plan_steps") or []:
        files.extend(step.get("files") or [])
    return files


def run_closed_world_diff_gate(
    *,
    repo_root: Path,
    policy_workspace: Path,
    artifact_root: Path,
    job: dict[str, Any],
    fix_ci_hints: list[str] | None = None,
) -> DiffGateResult:
    """Evaluate diff gate; promote raw_patch.diff to patch.diff on pass."""
    binding = job.get("fix_authorization") or {}
    allowed_files = list(binding.get("allowed_files") or [])

    policy = load_closed_world_policy(policy_workspace)
    unified_diff = read_unified_diff(repo_root)
    if not unified_diff and (artifact_root / RAW_PATCH_NAME).is_file():
        unified_diff = (artifact_root / RAW_PATCH_NAME).read_text(encoding="utf-8")

    blast_radius = BlastRadiusContext()
    pack_raw = job.get("context_pack")
    if pack_raw:
        if isinstance(pack_raw, ContextPack):
            blast_radius = pack_raw.blast_radius
        elif isinstance(pack_raw, dict):
            br_raw = pack_raw.get("blast_radius")
            if br_raw:
                blast_radius = BlastRadiusContext.model_validate(br_raw)

    result = evaluate_diff_gate(
        policy=policy,
        unified_diff=unified_diff,
        changed_files=collect_changed_files(repo_root),
        allowed_files=allowed_files,
        fix_ci_hints=fix_ci_hints or [],
        binding_ci_hints=list(binding.get("ci_hints") or []),
        blast_radius=blast_radius,
        binding_blast_radius_hash=binding.get("blast_radius_hash"),
        plan_step_files=_plan_step_files(binding),
        approval_id=binding.get("approval_id"),
        approval_target_id=binding.get("approval_target_id"),
        plan_run_id=binding.get("plan_run_id"),
    )

    gate_path = artifact_root / "diff_gate_result.json"
    gate_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")

    raw_path = artifact_root / RAW_PATCH_NAME
    approved_path = artifact_root / APPROVED_PATCH_NAME

    if result.passed:
        if unified_diff:
            approved_path.write_text(unified_diff, encoding="utf-8")
        elif raw_path.is_file():
            shutil.copy2(raw_path, approved_path)
        return result

    if approved_path.exists():
        approved_path.unlink()
    raise DiffGateError(result)


def promote_raw_patch(artifact_root: Path) -> str:
    raw_path = artifact_root / RAW_PATCH_NAME
    approved_path = artifact_root / APPROVED_PATCH_NAME
    if raw_path.is_file():
        shutil.copy2(raw_path, approved_path)
        return APPROVED_PATCH_NAME
    return ""
