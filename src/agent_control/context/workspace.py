"""Exact-SHA detached workspace for production ContextPack V2 evidence.

This module is the only production V2 path allowed to git clone/fetch/checkout.
Callers receive a Path for ``from_production(..., workspace_path)``. Providers
are not given a git-checkout API.
"""

from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from agent_shared.git_patch import git_run

if TYPE_CHECKING:
    from agent_control.config import Settings

__all__ = ["ExactShaWorkspaceError", "materialize_exact_sha_workspace"]

_SAFE_GIT_CONFIG = [
    ("core.hooksPath", "/dev/null"),
    ("core.askPass", ""),
    ("credential.helper", ""),
    ("filter.lfs.smudge", "git-lfs smudge --skip -- %f"),
    ("filter.lfs.process", "git-lfs filter-process --skip"),
    ("filter.lfs.required", "false"),
]


class ExactShaWorkspaceError(RuntimeError):
    """Fail-closed exact-SHA workspace materialization (missing or unfetchable SHA)."""

    def __init__(self, reason: str, message: str = "") -> None:
        self.reason = reason
        super().__init__(message or reason)


def materialize_exact_sha_workspace(
    *,
    repo_url: str,
    target_sha: str,
    dest: str | Path,
    settings: Settings | None = None,
) -> Path:
    """Clone ``repo_url`` and ``git checkout --detach`` at ``target_sha``.

    Fail closed if the SHA is missing or unfetchable. Never falls back to
    ``main`` or the current branch tip. After success, ``git rev-parse HEAD``
    equals ``target_sha`` and HEAD is detached (not a fast-forwardable branch).
    """
    requested = (target_sha or "").strip()
    if not requested:
        raise ExactShaWorkspaceError("missing_sha", "target_sha missing; cannot materialize workspace")

    work = Path(dest)
    if not str(work):
        raise ExactShaWorkspaceError("missing_dest", "workspace dest path is required")

    auth_url = _resolve_clone_url(repo_url, settings)
    env = _clone_env(auth_url)
    work.parent.mkdir(parents=True, exist_ok=True)
    if work.exists():
        _rmtree(work)

    created = False
    try:
        _clone_repo(auth_url, work, env)
        created = True
        _fetch_sha(work, requested, env)
        checkout = git_run(work, ["git", "checkout", "--detach", requested], env=env)
        if checkout.returncode != 0:
            raise ExactShaWorkspaceError(
                "unfetchable_sha",
                checkout.stderr.strip() or f"cannot checkout {requested}",
            )
        _assert_detached_at_sha(work, requested, env)
        _scrub_if_needed(work, repo_url)
        return work
    except ExactShaWorkspaceError:
        if created and work.exists():
            _rmtree(work)
        raise


def _is_file_repo(repo_url: str) -> bool:
    parsed = urlparse(repo_url)
    return parsed.scheme in ("", "file")


def _resolve_clone_url(repo_url: str, settings: Settings | None) -> str:
    if settings is None or _is_file_repo(repo_url):
        return repo_url
    from agent_control.git_auth import resolve_authenticated_repo_url

    return resolve_authenticated_repo_url(repo_url, settings)


def _clone_env(auth_url: str) -> dict[str, str]:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env.pop("GIT_ASKPASS", None)
    env.pop("SSH_ASKPASS", None)
    configs = list(_SAFE_GIT_CONFIG)
    if _is_file_repo(auth_url):
        configs.append(("protocol.file.allow", "always"))
    else:
        configs.append(("protocol.file.allow", "never"))
        configs.append(("protocol.ext.allow", "never"))
    existing = int(env.get("GIT_CONFIG_COUNT") or "0")
    env["GIT_CONFIG_COUNT"] = str(existing + len(configs))
    for i, (key, value) in enumerate(configs):
        idx = existing + i
        env[f"GIT_CONFIG_KEY_{idx}"] = key
        env[f"GIT_CONFIG_VALUE_{idx}"] = value
    return env


def _clone_repo(auth_url: str, work: Path, env: dict[str, str]) -> None:
    clone = git_run(
        work.parent,
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
        if work.exists():
            _rmtree(work)
        clone = git_run(
            work.parent,
            ["git", "clone", "--no-recurse-submodules", auth_url, str(work)],
            env=env,
        )
    if clone.returncode != 0:
        raise ExactShaWorkspaceError("clone_failed", clone.stderr.strip() or "git clone failed")


def _fetch_sha(work: Path, requested: str, env: dict[str, str]) -> None:
    git_run(work, ["git", "fetch", "--no-recurse-submodules", "origin", requested], env=env)


def _assert_detached_at_sha(work: Path, requested: str, env: dict[str, str]) -> None:
    symbolic = git_run(work, ["git", "symbolic-ref", "-q", "HEAD"], env=env)
    if symbolic.returncode == 0:
        raise ExactShaWorkspaceError(
            "not_detached",
            "workspace HEAD is a branch; refusing fast-forwardable checkout",
        )
    head = git_run(work, ["git", "rev-parse", "HEAD"], env=env)
    if head.returncode != 0:
        raise ExactShaWorkspaceError("head_unreadable", head.stderr.strip() or "cannot read HEAD")
    actual = head.stdout.strip()
    if actual != requested:
        raise ExactShaWorkspaceError(
            "head_mismatch",
            f"workspace HEAD {actual} != requested {requested}",
        )


def _scrub_if_needed(work: Path, repo_url: str) -> None:
    if _is_file_repo(repo_url):
        return
    from agent_shared.git_hygiene import scrub_clone_credentials, strip_token_from_url

    scrub_clone_credentials(work, token_free_remote=strip_token_from_url(repo_url))


def _rmtree(path: Path) -> None:
    def _onerror(func: object, p: str, _exc: object) -> None:
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)  # type: ignore[operator]
        except OSError:
            pass

    shutil.rmtree(path, onerror=_onerror)
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
