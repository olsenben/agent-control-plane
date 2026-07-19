"""Shared git clone hygiene for task and policy workspaces (V4.1.1 PR3)."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from agent_control.git_auth import git_non_interactive_env
from agent_shared.models.attestation import CredentialScrubReport

SAFE_GIT_CONFIG: list[tuple[str, str]] = [
    ("core.hooksPath", "/dev/null"),
    ("core.askPass", ""),
    ("credential.helper", ""),
    ("protocol.file.allow", "never"),
    ("protocol.ext.allow", "never"),
    ("filter.lfs.smudge", "git-lfs smudge --skip -- %f"),
    ("filter.lfs.process", "git-lfs filter-process --skip"),
    ("filter.lfs.required", "false"),
]

_TOKEN_IN_URL_RE = re.compile(r":[^/@\s]+@")


def apply_safe_git_config_env(
    env: dict[str, str],
    *,
    extra: list[tuple[str, str]] | None = None,
) -> dict[str, str]:
    """Merge SAFE_GIT_CONFIG into GIT_CONFIG_COUNT_* env entries."""
    out = dict(env)
    configs = list(SAFE_GIT_CONFIG)
    if extra:
        configs.extend(extra)
    # Preserve any existing GIT_CONFIG_* by appending after them
    existing = int(out.get("GIT_CONFIG_COUNT") or "0")
    out["GIT_CONFIG_COUNT"] = str(existing + len(configs))
    for i, (k, v) in enumerate(configs):
        idx = existing + i
        out[f"GIT_CONFIG_KEY_{idx}"] = k
        out[f"GIT_CONFIG_VALUE_{idx}"] = v
    out["GIT_TERMINAL_PROMPT"] = "0"
    out["GIT_CONFIG_NOSYSTEM"] = "1"
    out.pop("GIT_ASKPASS", None)
    out.pop("SSH_ASKPASS", None)
    return out


def hygienic_clone_env(auth_url: str) -> dict[str, str]:
    """Env for untrusted/task clones: non-interactive + safe config + nosystem."""
    base = {**os.environ, **git_non_interactive_env(repo_url=auth_url)}
    return apply_safe_git_config_env(base)


def _git(
    args: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def strip_token_from_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.username and not parsed.password:
        return url
    host = parsed.hostname or ""
    netloc = host
    if parsed.port:
        netloc = f"{host}:{parsed.port}"
    return urlunparse((parsed.scheme, netloc, parsed.path, "", "", ""))


def scrub_clone_credentials(
    workspace: Path,
    *,
    token_free_remote: str | None = None,
) -> CredentialScrubReport:
    """Strip auth from local git config after clone. Categories/names only."""
    report = CredentialScrubReport(
        hooks_disabled=True,
        askpass_cleared=True,
        credential_helper_cleared=True,
        git_config_nosystem=True,
        unsafe_protocols_disabled=True,
    )
    if not workspace.is_dir():
        return report

    env = apply_safe_git_config_env({**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    categories: list[str] = []
    names: list[str] = []

    # Rewrite or remove origin remote
    origin = _git(["git", "config", "--get", "remote.origin.url"], cwd=workspace, env=env)
    observed = (origin.stdout or "").strip() if origin.returncode == 0 else ""
    if observed and _TOKEN_IN_URL_RE.search(observed):
        categories.append("remote_url_credentials")
        names.append("remote.origin.url")
        report.token_bearing_remote_cleared = True
        clean = token_free_remote or strip_token_from_url(observed)
        _git(["git", "remote", "set-url", "origin", clean], cwd=workspace, env=env)
    elif token_free_remote and observed and observed != token_free_remote:
        _git(["git", "remote", "set-url", "origin", token_free_remote], cwd=workspace, env=env)
        categories.append("remote_url_rewritten")
        names.append("remote.origin.url")
        report.token_bearing_remote_cleared = True

    # Strip http.* extraheader auth if present
    extra = _git(["git", "config", "--get-regexp", r"^http\..*\.extraheader$"], cwd=workspace, env=env)
    if extra.returncode == 0 and (extra.stdout or "").strip():
        for line in extra.stdout.splitlines():
            key = line.split(" ", 1)[0].strip()
            if key:
                _git(["git", "config", "--unset-all", key], cwd=workspace, env=env)
                categories.append("http_extraheader")
                names.append(key)

    # Ensure credential.helper empty locally
    _git(["git", "config", "--local", "credential.helper", ""], cwd=workspace, env=env)
    _git(["git", "config", "--local", "core.hooksPath", "/dev/null"], cwd=workspace, env=env)
    _git(["git", "config", "--local", "core.askPass", ""], cwd=workspace, env=env)
    categories.extend(["credential_helper", "hooks_path", "askpass"])
    names.extend(["credential.helper", "core.hooksPath", "core.askPass"])

    # Final assert: no token-looking material in .git/config
    git_config = workspace / ".git" / "config"
    if git_config.is_file():
        cfg_text = git_config.read_text(encoding="utf-8", errors="replace")
        if _TOKEN_IN_URL_RE.search(cfg_text) or "Authorization:" in cfg_text:
            categories.append("residual_auth_material")
            names.append(".git/config")
            # Best-effort: rewrite origin again to stripped form
            if observed:
                clean = token_free_remote or strip_token_from_url(observed)
                _git(["git", "remote", "set-url", "origin", clean], cwd=workspace, env=env)
                report.token_bearing_remote_cleared = True

    report.categories_removed = sorted(set(categories))
    report.names_removed = sorted(set(names))
    return report


def assert_no_token_in_git_config(workspace: Path) -> None:
    git_config = workspace / ".git" / "config"
    if not git_config.is_file():
        return
    text = git_config.read_text(encoding="utf-8", errors="replace")
    if _TOKEN_IN_URL_RE.search(text) or "Authorization:" in text:
        raise RuntimeError("token_bearing_material_in_git_config")
