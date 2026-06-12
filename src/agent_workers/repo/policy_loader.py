"""Repository snapshot and policy loading."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import yaml

from agent_control.project_registry import resolve_project
from agent_shared.models.jobs import JobSafety
from agent_shared.models.policy import EffectivePolicy, PolicySource
from agent_workers.settings import WorkerSettings


def clone_repo(
    settings: WorkerSettings,
    repo_url: str,
    ref: str,
    dest: Path,
) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)
    env = {}
    if settings.git_ro_key_path and settings.git_ro_key_path.exists():
        env["GIT_SSH_COMMAND"] = f"ssh -i {settings.git_ro_key_path} -o StrictHostKeyChecking=no"
    subprocess.run(
        ["git", "clone", "--depth", "1", "--branch", ref.replace("refs/heads/", ""), repo_url, str(dest)],
        check=True,
        capture_output=True,
        env={**os.environ, **env},
    )
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
    policy_ref = job.get("policy_ref", cfg.protected_policy_ref)
    loaded_files: list[str] = []
    source = "repo"

    agent_config = workspace / ".agent" / "agent-config.yml"
    agents_yml = workspace / ".agent" / "agents.yml"
    agents_md = workspace / "AGENTS.md"

    for candidate in (agents_md, agent_config, agents_yml):
        if candidate.exists():
            loaded_files.append(str(candidate.relative_to(workspace)))

    if not agent_config.exists() and cfg.bootstrap_default_policy:
        source = "platform_default"
        warnings.append("missing .agent/agent-config.yml; using platform_default inspect policy")
        if not agents_md.exists():
            warnings.append("missing AGENTS.md")

    if not agent_config.exists() and not cfg.bootstrap_default_policy:
        raise FileNotFoundError(".agent/agent-config.yml not found and repo not allowlisted for bootstrap")

    if agents_md.exists() and str(agents_md.relative_to(workspace)) not in loaded_files:
        loaded_files.append("AGENTS.md")

    policy_source = PolicySource(
        source=source,
        policy_ref=policy_ref,
        policy_sha=_head_sha(workspace),
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
    )
    return policy_source, effective, warnings


def _head_sha(workspace: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=workspace,
            check=True,
            capture_output=True,
            text=True,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def write_policy_artifacts(run_path: Path, policy_source: PolicySource, effective: EffectivePolicy) -> None:
    (run_path / "policy_source.json").write_text(
        policy_source.model_dump_json(indent=2),
        encoding="utf-8",
    )
    (run_path / "effective_policy.json").write_text(
        effective.model_dump_json(indent=2),
        encoding="utf-8",
    )
