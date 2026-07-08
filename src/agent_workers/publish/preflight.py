"""Publish preflight checks before git commit (Slice 6D.1)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from agent_shared.models.jobs import RLMJob
from agent_workers.gates.runner import APPROVED_PATCH_NAME, collect_changed_files
from agent_workers.rlm.output_quality import normalize_patch_path
from agent_workers.settings import WorkerSettings


class PublishPreflightError(Exception):
    def __init__(self, stage: str, message: str):
        self.stage = stage
        super().__init__(message)


def _git_run(repo_root: Path, cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )


def _git_identity_configured(repo_root: Path) -> bool:
    for scope in ([], ["--global"]):
        name = _git_run(repo_root, ["git", "config", *scope, "user.name"])
        email = _git_run(repo_root, ["git", "config", *scope, "user.email"])
        if name.returncode == 0 and email.returncode == 0:
            if name.stdout.strip() and email.stdout.strip():
                return True
    return False


def run_publish_preflight(
    *,
    repo_workspace: Path,
    artifact_root: Path,
    job: RLMJob,
    settings: WorkerSettings,
    allowed_files: list[str],
) -> None:
    """Workspace-mode preflight: patch already applied; do not git apply --check."""
    if not settings.fix_remote_publish_enabled:
        raise PublishPreflightError("publish_preflight", "FIX_REMOTE_PUBLISH_ENABLED=false")
    if not job.safety.allow_push:
        raise PublishPreflightError("publish_preflight", "Publish disabled on job (allow_push=false)")

    patch_path = artifact_root / APPROVED_PATCH_NAME
    if not patch_path.is_file() or patch_path.stat().st_size == 0:
        raise PublishPreflightError("publish_preflight", "patch.diff missing or empty")

    if not _git_identity_configured(repo_workspace):
        raise PublishPreflightError(
            "publish_preflight",
            "Git author identity not configured (user.name / user.email)",
        )

    diff_check = _git_run(repo_workspace, ["git", "diff", "--check"])
    if diff_check.returncode != 0:
        raise PublishPreflightError(
            "publish_preflight",
            (diff_check.stderr or diff_check.stdout or "git diff --check failed").strip(),
        )

    changed = collect_changed_files(repo_workspace)
    if not changed:
        raise PublishPreflightError("publish_preflight", "Working tree has no changed files")

    if allowed_files:
        allowed_norm = {normalize_patch_path(p) for p in allowed_files}
        changed_norm = {normalize_patch_path(p) for p in changed}
        if not (changed_norm & allowed_norm):
            raise PublishPreflightError(
                "publish_preflight",
                "No stageable changes in allowed file scope",
            )
