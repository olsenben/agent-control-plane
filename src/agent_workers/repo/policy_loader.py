"""Repository snapshot and policy loading."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import yaml

from agent_control.git_auth import (
    authenticated_repo_url_from_credentials,
    git_non_interactive_env,
)
from agent_control.project_registry import (
    PolicySourcePin,
    PolicySourcePinError,
    normalize_policy_remote,
    pin_from_job_fields,
    resolve_project,
)
from agent_shared.models.jobs import JobSafety
from agent_shared.models.policy import EffectivePolicy, PolicySource
from agent_workers.settings import WorkerSettings

_SAFE_GIT_CONFIG = [
    ("core.hooksPath", "/dev/null"),
    ("core.askPass", ""),
    ("credential.helper", ""),
    ("filter.lfs.smudge", "git-lfs smudge --skip -- %f"),
    ("filter.lfs.process", "git-lfs filter-process --skip"),
    ("filter.lfs.required", "false"),
]


class PolicyWorkspaceError(RuntimeError):
    """Pinned policy workspace could not be prepared or verified."""


def _policy_clone_env(auth_url: str) -> dict[str, str]:
    env = {**os.environ, **git_non_interactive_env(repo_url=auth_url)}
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env.pop("GIT_ASKPASS", None)
    env.pop("SSH_ASKPASS", None)
    configs = list(_SAFE_GIT_CONFIG)
    env["GIT_CONFIG_COUNT"] = str(len(configs))
    for i, (k, v) in enumerate(configs):
        env[f"GIT_CONFIG_KEY_{i}"] = k
        env[f"GIT_CONFIG_VALUE_{i}"] = v
    return env


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


def _remote_identity_matches(observed_url: str, expected_remote: str) -> bool:
    try:
        return normalize_policy_remote(observed_url) == normalize_policy_remote(expected_remote)
    except PolicySourcePinError:
        return False


def _make_tree_readonly(root: Path) -> None:
    """Best-effort: deny writes to policy tree (Unix). Skipped on failure."""
    try:
        for dirpath, _dirnames, filenames in os.walk(root):
            try:
                os.chmod(dirpath, stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP)
            except OSError:
                pass
            for name in filenames:
                path = Path(dirpath) / name
                try:
                    mode = path.stat().st_mode
                    os.chmod(path, mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
                except OSError:
                    pass
    except OSError:
        pass


def verify_pinned_policy_workspace(workspace: Path, pin: PolicySourcePin) -> None:
    """Fail closed unless HEAD and remote identity match the CT103 pin."""
    if not workspace.is_dir():
        raise PolicyWorkspaceError(f"policy workspace missing: {workspace}")

    head = _git(["git", "rev-parse", "HEAD"], cwd=workspace)
    if head.returncode != 0:
        raise PolicyWorkspaceError(f"cannot read HEAD: {head.stderr.strip()}")
    head_sha = head.stdout.strip()
    if head_sha != pin.policy_source_sha:
        raise PolicyWorkspaceError(
            f"policy HEAD {head_sha} != pinned {pin.policy_source_sha}"
        )

    origin = _git(["git", "config", "--get", "remote.origin.url"], cwd=workspace)
    observed = (origin.stdout or "").strip() if origin.returncode == 0 else ""
    if observed:
        if not _remote_identity_matches(observed, pin.policy_source_remote):
            raise PolicyWorkspaceError(
                f"policy remote identity mismatch: observed={observed!r} "
                f"expected={pin.policy_source_remote!r}"
            )
        return

    marker = workspace / ".git" / "policy_source_remote"
    if marker.is_file():
        recorded = marker.read_text(encoding="utf-8").strip()
        if not _remote_identity_matches(recorded, pin.policy_source_remote):
            raise PolicyWorkspaceError(
                f"policy remote marker mismatch: {recorded!r}"
            )
        return
    raise PolicyWorkspaceError("policy remote origin missing after checkout")


def checkout_pinned_policy_workspace(
    settings: WorkerSettings,
    pin: PolicySourcePin,
    dest: Path,
    *,
    clone_url: str | None = None,
) -> Path:
    """Detached checkout of ``pin.policy_source_sha`` into a separate policy workspace."""
    if not pin.policy_source_sha.strip():
        raise PolicyWorkspaceError("missing policy_source_sha")

    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)

    from urllib.parse import urlunparse

    repo_url = clone_url or pin.policy_source_remote
    # Ensure .git suffix for clone when normalize stripped it
    parsed = urlparse(repo_url)
    path = (parsed.path or "").rstrip("/")
    if not path.endswith(".git"):
        path = f"{path}.git"
    repo_url = urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))

    # Host check against configured pin remote (anti same-object-name remote)
    try:
        if normalize_policy_remote(repo_url) != normalize_policy_remote(pin.policy_source_remote):
            raise PolicyWorkspaceError(
                f"clone url {repo_url!r} does not match pin remote {pin.policy_source_remote!r}"
            )
    except PolicySourcePinError as exc:
        raise PolicyWorkspaceError(str(exc)) from exc

    authed_url = authenticated_repo_url_from_credentials(repo_url)
    env = _policy_clone_env(authed_url)
    if settings.git_ro_key_path and settings.git_ro_key_path.exists():
        env["GIT_SSH_COMMAND"] = f"ssh -i {settings.git_ro_key_path} -o StrictHostKeyChecking=no"

    clone = _git(
        ["git", "clone", "--no-recurse-submodules", "--filter=blob:none", authed_url, str(dest)],
        env=env,
    )
    if clone.returncode != 0:
        if dest.exists():
            shutil.rmtree(dest)
        clone = _git(
            ["git", "clone", "--no-recurse-submodules", authed_url, str(dest)],
            env=env,
        )
    if clone.returncode != 0:
        raise PolicyWorkspaceError(clone.stderr.strip() or "policy clone failed")

    # Record expected remote before any rewrite
    git_dir = dest / ".git"
    (git_dir / "policy_source_remote").write_text(pin.policy_source_remote + "\n", encoding="utf-8")

    fetch = _git(
        ["git", "fetch", "--no-recurse-submodules", "origin", pin.policy_source_sha],
        cwd=dest,
        env=env,
    )
    co = _git(
        ["git", "checkout", "--detach", pin.policy_source_sha],
        cwd=dest,
        env=env,
    )
    if co.returncode != 0:
        raise PolicyWorkspaceError(
            (co.stderr or fetch.stderr or f"cannot checkout {pin.policy_source_sha}").strip()
        )

    # Strip token-bearing origin URL; keep identity in marker for verify
    _git(["git", "remote", "set-url", "origin", pin.policy_source_remote], cwd=dest, env=env)

    verify_pinned_policy_workspace(dest, pin)
    _make_tree_readonly(dest)
    return dest


def clone_repo(
    settings: WorkerSettings,
    repo_url: str,
    ref: str,
    dest: Path,
) -> Path:
    """Clone a branch tip into the writable agent/task workspace (not policy authority)."""
    from agent_shared.git_hygiene import hygienic_clone_env, scrub_clone_credentials, strip_token_from_url
    from urllib.parse import urlparse, urlunparse

    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)
    authed_url = authenticated_repo_url_from_credentials(repo_url)
    env = hygienic_clone_env(authed_url)
    if settings.git_ro_key_path and settings.git_ro_key_path.exists():
        env["GIT_SSH_COMMAND"] = f"ssh -i {settings.git_ro_key_path} -o StrictHostKeyChecking=no"
    subprocess.run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            "--branch",
            ref.replace("refs/heads/", ""),
            authed_url,
            str(dest),
        ],
        check=True,
        capture_output=True,
        env=env,
    )
    # Token-free remote for scrub target
    parsed = urlparse(repo_url)
    path = (parsed.path or "").rstrip("/")
    if not path.endswith(".git"):
        path = f"{path}.git"
    token_free = urlunparse((parsed.scheme, parsed.netloc.split("@")[-1], path, "", "", ""))
    scrub_clone_credentials(dest, token_free_remote=token_free or strip_token_from_url(authed_url))
    return dest


def load_platform_default_policy() -> dict:
    path = Path(__file__).resolve().parents[1] / "config" / "platform_default" / "inspect_policy.yml"
    if not path.exists():
        return {"agents": {"explainer": {"tools": ["read_repo"]}}, "tests": {"allowed_commands": []}}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_policy(
    workspace: Path,
    job: dict,
    settings: WorkerSettings,
) -> tuple[PolicySource, EffectivePolicy, list[str]]:
    warnings: list[str] = []
    cfg = resolve_project(job["project"])
    pin = pin_from_job_fields(
        policy_source_repo=str(job.get("policy_source_repo") or ""),
        policy_source_remote=str(job.get("policy_source_remote") or ""),
        policy_source_ref=str(job.get("policy_source_ref") or ""),
        policy_source_sha=str(job.get("policy_source_sha") or ""),
        policy_schema_version=str(job.get("policy_schema_version") or ""),
        project=str(job.get("project") or ""),
        repo_url=str(job.get("repo_url") or ""),
        policy_ref=str(job.get("policy_ref") or cfg.protected_policy_ref),
    )
    if pin is None:
        raise PolicyWorkspaceError("job missing policy_source_sha pin")
    verify_pinned_policy_workspace(workspace, pin)

    policy_ref = pin.policy_source_ref
    loaded_files: list[str] = []
    source = "repo"

    agent_config = workspace / ".agent" / "agent-config.yml"
    agents_yml = workspace / ".agent" / "agents.yml"
    agents_md = workspace / "AGENTS.md"

    for candidate in (agents_md, agent_config, agents_yml):
        if candidate.exists():
            loaded_files.append(str(candidate.relative_to(workspace)))

    repo_policy = workspace / ".agent" / "policies" / "closed_world.yaml"
    if repo_policy.exists():
        loaded_files.append(".agent/policies/closed_world.yaml")

    if not agent_config.exists() and cfg.bootstrap_default_policy:
        source = "platform_default"
        warnings.append("missing .agent/agent-config.yml; using platform_default inspect policy")
        if not agents_md.exists():
            warnings.append("missing AGENTS.md")

    if not agent_config.exists() and not cfg.bootstrap_default_policy:
        raise FileNotFoundError(".agent/agent-config.yml not found and repo not allowlisted for bootstrap")

    if agents_md.exists() and str(agents_md.relative_to(workspace)) not in loaded_files:
        loaded_files.append("AGENTS.md")

    from agent_control.sandbox.tool_policy import load_tool_policy_from_workspace

    tool_policy = load_tool_policy_from_workspace(workspace)
    if tool_policy.loaded_path and tool_policy.status != "empty_missing":
        if tool_policy.loaded_path not in loaded_files:
            loaded_files.append(tool_policy.loaded_path)
    elif tool_policy.status == "empty_missing":
        warnings.append("tools_yaml_missing_empty_allowance")
    if tool_policy.status in ("empty_invalid", "empty_unsupported"):
        warnings.extend(tool_policy.warnings)
        warnings.append(f"tools_yaml_{tool_policy.status}_empty_allowance")
    else:
        warnings.extend(tool_policy.warnings)

    policy_source = PolicySource(
        source=source,
        policy_ref=policy_ref,
        policy_sha=pin.policy_source_sha,
        policy_source_repo=pin.policy_source_repo,
        policy_source_remote=pin.policy_source_remote,
        policy_source_ref=pin.policy_source_ref,
        policy_source_sha=pin.policy_source_sha,
        policy_schema_version=pin.policy_schema_version,
        task_ref=job.get("task_ref"),
        task_sha=job.get("target_sha"),
        loaded_files=loaded_files,
        warnings=warnings,
    )

    allowed_tools = ["read_repo", "search_code", "read_context"]
    if source == "platform_default":
        default = load_platform_default_policy()
        agent_name = job.get("agent", "explainer")
        allowed_tools = default.get("agents", {}).get(agent_name, {}).get("tools", allowed_tools)

    safety = JobSafety.model_validate(job.get("safety", {}))

    effective = EffectivePolicy(
        run_id=job["run_id"],
        flow=job["flow"],
        agent=job["agent"],
        risk_class=str(job.get("risk_class", "read_only")),
        safety=safety,
        allowed_tools=allowed_tools,
        protected_paths=[
            ".agent/**",
            ".gitea/workflows/**",
            ".github/workflows/**",
            "CODEOWNERS",
            ".env*",
        ],
        warnings=warnings,
        allowed_command_ids=list(tool_policy.allowed_command_ids),
        command_constraints={
            cid: c.to_dict() for cid, c in tool_policy.constraints.items()
        },
        deny_freeform_shell=tool_policy.deny_freeform_shell,
        allow_network=tool_policy.allow_network,
        tool_policy_status=tool_policy.status,
        command_registry_hash=tool_policy.command_registry_hash,
        effective_command_policy_hash=tool_policy.effective_command_policy_hash,
        command_policy_hash_algorithm=tool_policy.hash_algorithm,
    )
    return policy_source, effective, warnings


def write_policy_artifacts(run_path: Path, policy_source: PolicySource, effective: EffectivePolicy) -> None:
    (run_path / "policy_source.json").write_text(
        policy_source.model_dump_json(indent=2),
        encoding="utf-8",
    )
    (run_path / "effective_policy.json").write_text(
        effective.model_dump_json(indent=2),
        encoding="utf-8",
    )
