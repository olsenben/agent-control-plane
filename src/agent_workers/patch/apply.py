"""Apply FixResult to run workspace with post-apply diff subset assertion."""

from __future__ import annotations

import subprocess
from pathlib import Path

from agent_shared.models.fix import FixFileChange, FixResult
from agent_shared.patch_paths import PatchPathError, validate_allowed_patch_path


class ApplyFixError(Exception):
    """Raised when fix apply or post-apply assertion fails."""

    def __init__(
        self,
        stage: str,
        message: str,
        *,
        allowed_files: list[str],
        changed_files_so_far: list[str] | None = None,
    ):
        self.stage = stage
        self.allowed_files = allowed_files
        self.changed_files_so_far = changed_files_so_far or []
        super().__init__(message)


def _git_diff_name_only(repo_root: Path) -> list[str]:
    proc = subprocess.run(
        ["git", "diff", "--name-only"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise ApplyFixError(
            "post_apply_diff_assert",
            proc.stderr.strip() or "git diff --name-only failed",
            allowed_files=[],
        )
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _validate_change_path(change: FixFileChange, allowed_files: list[str]) -> str:
    try:
        return validate_allowed_patch_path(change.path, allowed_files)
    except PatchPathError as exc:
        raise ApplyFixError("apply", str(exc), allowed_files=allowed_files) from exc


def _apply_single_change(repo_root: Path, change: FixFileChange, normalized_path: str) -> None:
    target = repo_root / normalized_path
    if change.edit_kind == "create":
        if target.exists():
            raise ApplyFixError(
                "apply",
                f"create requested but file exists: {normalized_path!r}",
                allowed_files=[],
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(change.content, encoding="utf-8")
        return

    if not target.is_file():
        raise ApplyFixError(
            "apply",
            f"{change.edit_kind} requested but file missing: {normalized_path!r}",
            allowed_files=[],
        )

    if change.edit_kind == "replace":
        target.write_text(change.content, encoding="utf-8")
    elif change.edit_kind == "append":
        existing = target.read_text(encoding="utf-8")
        target.write_text(existing + change.content, encoding="utf-8")
    else:
        raise ApplyFixError(
            "apply",
            f"unsupported edit_kind: {change.edit_kind!r}",
            allowed_files=[],
        )


def apply_fix_to_workspace(
    repo_root: Path,
    fix: FixResult,
    allowed_files: list[str],
    artifact_root: Path,
) -> str:
    """Apply changes under repo_root; write raw_patch.diff; return relative path."""
    changed_so_far: list[str] = []
    try:
        for change in fix.changes:
            normalized = _validate_change_path(change, allowed_files)
            _apply_single_change(repo_root, change, normalized)
            changed_so_far.append(normalized)

        changed_files = _git_diff_name_only(repo_root)
        allowed_set = set(allowed_files)
        extra = sorted(set(changed_files) - allowed_set)
        if extra:
            raise ApplyFixError(
                "post_apply_diff_assert",
                f"changed files exceed allowed_files: {extra}",
                allowed_files=allowed_files,
                changed_files_so_far=changed_files,
            )

        proc = subprocess.run(
            ["git", "diff"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise ApplyFixError(
                "artifact_write",
                proc.stderr.strip() or "git diff failed",
                allowed_files=allowed_files,
                changed_files_so_far=changed_files,
            )

        patch_path = artifact_root / "raw_patch.diff"
        patch_path.write_text(proc.stdout, encoding="utf-8")
        return "raw_patch.diff"
    except ApplyFixError:
        raise
    except OSError as exc:
        raise ApplyFixError(
            "apply",
            str(exc),
            allowed_files=allowed_files,
            changed_files_so_far=changed_so_far,
        ) from exc
