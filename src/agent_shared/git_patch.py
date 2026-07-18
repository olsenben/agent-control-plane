"""Pure git patch/diff/index helpers — no credentials, push, or PR API."""

from __future__ import annotations

import subprocess
from pathlib import Path


class GitPatchError(Exception):
    pass


def git_run(
    repo_root: Path,
    cmd: list[str],
    *,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def git_head(repo_root: Path) -> str:
    proc = git_run(repo_root, ["git", "rev-parse", "HEAD"])
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def git_write_tree(repo_root: Path) -> str:
    proc = git_run(repo_root, ["git", "write-tree"])
    if proc.returncode != 0:
        raise GitPatchError(proc.stderr or "git write-tree failed")
    return proc.stdout.strip()


def apply_patch_to_index(repo_root: Path, patch_path: Path) -> None:
    """Apply unified diff to the index without running hooks or filters."""
    proc = git_run(
        repo_root,
        ["git", "apply", "--index", "--whitespace=nowarn", str(patch_path)],
    )
    if proc.returncode != 0:
        raise GitPatchError(proc.stderr or "git apply --index failed")


def commit_tree(
    repo_root: Path,
    *,
    tree_sha: str,
    parent_sha: str,
    message: str,
    env: dict[str, str] | None = None,
) -> str:
    """Create a commit via plumbing (bypasses commit hooks)."""
    proc = git_run(
        repo_root,
        ["git", "commit-tree", tree_sha, "-p", parent_sha, "-m", message],
        env=env,
    )
    if proc.returncode != 0:
        raise GitPatchError(proc.stderr or "git commit-tree failed")
    return proc.stdout.strip()


def verify_commit_parent_and_tree(
    repo_root: Path,
    commit_sha: str,
    *,
    expected_parent: str,
    expected_tree: str,
) -> None:
    parent = git_run(repo_root, ["git", "rev-parse", f"{commit_sha}^"]).stdout.strip()
    tree = git_run(repo_root, ["git", "rev-parse", f"{commit_sha}^{{tree}}"]).stdout.strip()
    if parent != expected_parent:
        raise GitPatchError(f"Commit parent {parent} != expected {expected_parent}")
    if tree != expected_tree:
        raise GitPatchError(f"Commit tree {tree} != expected {expected_tree}")


def status_porcelain(repo_root: Path) -> list[str]:
    proc = git_run(repo_root, ["git", "status", "--porcelain=v1"])
    return [line for line in proc.stdout.splitlines() if line.strip()]


def collect_changed_paths(repo_root: Path) -> list[str]:
    """Changed paths relative to HEAD (tracked + untracked), excluding ignore."""
    names: list[str] = []
    diff = git_run(repo_root, ["git", "diff", "--name-only", "HEAD"])
    for line in diff.stdout.splitlines():
        p = line.strip()
        if p:
            names.append(p)
    untracked = git_run(repo_root, ["git", "ls-files", "--others", "--exclude-standard"])
    for line in untracked.stdout.splitlines():
        p = line.strip()
        if p and p not in names:
            names.append(p)
    return names


def stage_allowed_files(repo_root: Path, allowed_files: list[str]) -> list[str]:
    """Stage only allowlisted paths; reject residue outside the allowlist."""
    changed = collect_changed_paths(repo_root)
    to_stage = [p for p in changed if p in allowed_files]
    if not to_stage:
        raise GitPatchError("No allowed changed files to stage")
    proc = git_run(repo_root, ["git", "add", "-A", "--", *to_stage])
    if proc.returncode != 0:
        raise GitPatchError(proc.stderr or "git add failed")
    staged_proc = git_run(repo_root, ["git", "diff", "--cached", "--name-only"])
    staged = [line.strip() for line in staged_proc.stdout.splitlines() if line.strip()]
    allowed_set = set(allowed_files)
    extra_staged = [p for p in staged if p not in allowed_set]
    if extra_staged:
        raise GitPatchError(f"Staged files outside allowlist: {extra_staged}")
    for line in status_porcelain(repo_root):
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if path not in allowed_set and path not in staged:
            raise GitPatchError(f"Unstaged side effect outside allowlist: {path}")
    return staged
