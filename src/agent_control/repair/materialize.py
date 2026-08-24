"""Workspace materialization for verify-repair (VExp W2-C)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from agent_shared.models.fix import FixResult
from agent_workers.patch.apply import ApplyFixError, apply_fix_to_workspace


class MaterializeError(RuntimeError):
    """Canonical workspace materialization failed."""


def materialize(
    *,
    base_workspace: Path,
    snapshot_sha: str,
    fix_result: FixResult,
    target: Path,
    allowed_files: list[str] | None = None,
    artifact_root: Path | None = None,
) -> Path:
    """Create a disposable workspace at ``target`` with exact SHA + FixResult applied."""
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(
        base_workspace,
        target,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"),
        dirs_exist_ok=False,
    )
    _reset_to_sha(target, snapshot_sha)
    art = artifact_root or target / ".artifacts"
    art.mkdir(parents=True, exist_ok=True)
    try:
        apply_fix_to_workspace(
            target,
            fix_result,
            allowed_files=allowed_files or list(fix_result.files_changed),
            artifact_root=art,
        )
    except ApplyFixError as exc:
        raise MaterializeError(str(exc)) from exc
    return target


def _reset_to_sha(workspace: Path, sha: str) -> None:
    actual = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=workspace,
        text=True,
    ).strip()
    if actual != sha:
        subprocess.check_call(["git", "reset", "--hard", sha], cwd=workspace)
        subprocess.check_call(["git", "clean", "-fdx"], cwd=workspace)
