"""Independent CT103 patch validation (snapshot + plumbing; no repo code execution)."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from agent_control.config import Settings
from agent_control.git_auth import git_non_interactive_env, resolve_authenticated_repo_url
from agent_shared.bundles.inbox import sha256_file
from agent_shared.closed_world.gate import evaluate_diff_gate
from agent_shared.closed_world.loader import load_closed_world_policy
from agent_shared.git_patch import (
    GitPatchError,
    apply_patch_to_index,
    commit_tree,
    git_run,
    git_write_tree,
    status_porcelain,
    verify_commit_parent_and_tree,
)
from agent_shared.models.approval import FixAuthorizationBinding
from agent_shared.models.bundle import PatchBundleManifest
from agent_shared.models.diff_gate import DiffGateResult


class ValidationError(Exception):
    def __init__(self, reason: str, message: str = ""):
        self.reason = reason
        super().__init__(message or reason)


@dataclass(frozen=True)
class ValidatedCommit:
    trusted_base_sha: str
    result_tree_sha: str
    commit_sha: str
    patch_sha256: str
    gate_result: DiffGateResult
    workspace: Path
    producer_tree_sha: str | None


_SAFE_GIT_CONFIG = [
    ("core.hooksPath", "/dev/null"),
    ("core.askPass", ""),
    ("filter.lfs.smudge", "git-lfs smudge --skip -- %f"),
    ("filter.lfs.process", "git-lfs filter-process --skip"),
    ("filter.lfs.required", "false"),
]


def _safe_clone_env(auth_url: str, settings: Settings) -> dict[str, str]:
    _ = git_non_interactive_env(settings, repo_url=auth_url)  # ensure settings side effects
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    configs = [("credential.helper", "")] + list(_SAFE_GIT_CONFIG)
    env["GIT_CONFIG_COUNT"] = str(len(configs))
    for i, (k, v) in enumerate(configs):
        env[f"GIT_CONFIG_KEY_{i}"] = k
        env[f"GIT_CONFIG_VALUE_{i}"] = v
    return env


def _validate_host(repo_url: str, allowed_base: str) -> None:
    parsed = urlparse(repo_url)
    host = (parsed.hostname or "").lower()
    allowed = urlparse(allowed_base if "://" in allowed_base else f"https://{allowed_base}")
    allowed_host = (allowed.hostname or "").lower()
    if host != allowed_host:
        raise ValidationError("remote_host_rejected", f"host {host!r} != {allowed_host!r}")


def _changed_files_from_index(repo: Path) -> list[str]:
    proc = git_run(repo, ["git", "diff", "--cached", "--name-only"])
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _unified_diff_from_index(repo: Path) -> str:
    proc = git_run(repo, ["git", "diff", "--cached"])
    return proc.stdout or ""


def prepare_workspace_at_sha(
    *,
    settings: Settings,
    repo_url: str,
    trusted_sha: str,
    cache_dir: Path,
    work_name: str,
) -> Path:
    """Shallow fetch of exact SHA into a CT103-private disposable workspace."""
    _validate_host(repo_url, settings.gitea_base_url)
    auth_url = resolve_authenticated_repo_url(repo_url, settings)
    cache_dir.mkdir(parents=True, exist_ok=True)
    work = cache_dir / "publish-worktrees" / work_name
    if work.exists():
        shutil.rmtree(work)
    work.parent.mkdir(parents=True, exist_ok=True)
    env = _safe_clone_env(auth_url, settings)

    # Bare-ish: clone then fetch exact SHA (no recurse-submodules)
    clone = git_run(
        cache_dir,
        [
            "git",
            "clone",
            "--no-recurse-submodules",
            "--filter=blob:none",
            auth_url,
            str(work),
        ],
        env=env,
    )
    if clone.returncode != 0:
        # Fallback without partial clone
        if work.exists():
            shutil.rmtree(work)
        clone = git_run(
            cache_dir,
            ["git", "clone", "--no-recurse-submodules", auth_url, str(work)],
            env=env,
        )
    if clone.returncode != 0:
        raise ValidationError("clone_failed", clone.stderr or "git clone failed")

    fetch = git_run(
        work,
        ["git", "fetch", "--no-recurse-submodules", "origin", trusted_sha],
        env=env,
    )
    if fetch.returncode != 0:
        # try checkout if already present
        pass
    co = git_run(work, ["git", "checkout", "--detach", trusted_sha], env=env)
    if co.returncode != 0:
        raise ValidationError("checkout_failed", co.stderr or f"cannot checkout {trusted_sha}")
    return work


def validate_and_commit(
    *,
    settings: Settings,
    snapshot_dir: Path,
    manifest: PatchBundleManifest,
    binding: FixAuthorizationBinding,
    repo_url: str,
    trusted_base_sha: str,
    commit_message: str,
    policy_workspace: Path | None = None,
) -> ValidatedCommit:
    """Snapshot → apply --index → closed-world gate → commit-tree.

    ``producer_tree_sha`` is integrity-only (must match if present).
    Authorization uses ``trusted_base_sha`` + ``binding`` only.
    """
    if manifest.producer_base_sha != trusted_base_sha:
        raise ValidationError(
            "base_sha_mismatch",
            f"producer_base_sha {manifest.producer_base_sha} != trusted {trusted_base_sha}",
        )

    patch_path = snapshot_dir / manifest.patch_filename
    if not patch_path.is_file() or patch_path.is_symlink():
        raise ValidationError("patch_missing")
    if sha256_file(patch_path) != manifest.patch_sha256:
        raise ValidationError("patch_hash_mismatch")

    work = prepare_workspace_at_sha(
        settings=settings,
        repo_url=repo_url,
        trusted_sha=trusted_base_sha,
        cache_dir=settings.agent_cache_dir,
        work_name=f"{manifest.run_id}-{manifest.bundle_id}",
    )

    try:
        apply_patch_to_index(work, patch_path)
    except GitPatchError as exc:
        raise ValidationError("apply_failed", str(exc)) from exc

    residue = status_porcelain(work)
    # After --index apply, working tree may still show changes; require no *untracked* surprises
    for line in residue:
        if line.startswith("??"):
            raise ValidationError("untracked_residue", line)

    changed = _changed_files_from_index(work)
    allowed = list(binding.allowed_files)
    extra = [p for p in changed if p not in allowed]
    if extra:
        raise ValidationError("scope_violation", f"files outside allowlist: {extra}")

    unified = _unified_diff_from_index(work)
    policy_root = policy_workspace or work
    try:
        policy = load_closed_world_policy(policy_root)
    except Exception:
        # Fail closed with empty/default policy loader behavior
        from agent_shared.closed_world.policy import ClosedWorldPolicy

        policy = ClosedWorldPolicy()

    plan_step_files: list[str] = []
    for step in binding.plan_steps or []:
        plan_step_files.extend(step.files)

    gate = evaluate_diff_gate(
        policy=policy,
        unified_diff=unified,
        changed_files=changed,
        allowed_files=allowed,
        fix_ci_hints=None,
        binding_ci_hints=list(binding.ci_hints) if binding.ci_hints else None,
        binding_blast_radius_hash=binding.blast_radius_hash,
        plan_step_files=plan_step_files or None,
        approval_id=binding.approval_id,
        approval_target_id=binding.approval_target_id,
        plan_run_id=binding.plan_run_id,
    )
    if not gate.passed:
        raise ValidationError(
            "diff_gate_failed",
            ",".join(gate.violation_codes()) or "gate failed",
        )

    try:
        tree_sha = git_write_tree(work)
    except GitPatchError as exc:
        raise ValidationError("write_tree_failed", str(exc)) from exc

    if manifest.producer_tree_sha and manifest.producer_tree_sha != tree_sha:
        raise ValidationError(
            "producer_tree_mismatch",
            f"producer_tree_sha {manifest.producer_tree_sha} != {tree_sha}",
        )

    try:
        commit_sha = commit_tree(
            work,
            tree_sha=tree_sha,
            parent_sha=trusted_base_sha,
            message=commit_message,
            env=_safe_clone_env(resolve_authenticated_repo_url(repo_url, settings), settings),
        )
        verify_commit_parent_and_tree(
            work,
            commit_sha,
            expected_parent=trusted_base_sha,
            expected_tree=tree_sha,
        )
    except GitPatchError as exc:
        raise ValidationError("commit_failed", str(exc)) from exc

    # Point HEAD at constructed commit without hooks
    git_run(work, ["git", "update-ref", "HEAD", commit_sha])

    return ValidatedCommit(
        trusted_base_sha=trusted_base_sha,
        result_tree_sha=tree_sha,
        commit_sha=commit_sha,
        patch_sha256=manifest.patch_sha256,
        gate_result=gate,
        workspace=work,
        producer_tree_sha=manifest.producer_tree_sha,
    )
