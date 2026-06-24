"""Load closed-world policy from repo workspace or platform default."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from agent_shared.closed_world.policy import ClosedWorldPolicy

_PLATFORM_DEFAULT = (
    Path(__file__).resolve().parents[2]
    / "agent_workers"
    / "config"
    / "platform_default"
    / "closed_world.yml"
)


def _merge_elevated_approval(raw: dict[str, Any]) -> list[str]:
    elevated = list(raw.get("requires_elevated_approval") or [])
    legacy = list(raw.get("requires_human_approval") or [])
    seen: set[str] = set()
    merged: list[str] = []
    for item in elevated + legacy:
        if item not in seen:
            seen.add(item)
            merged.append(item)
    return merged


def _parse_policy_dict(raw: dict[str, Any], sources: list[str]) -> ClosedWorldPolicy:
    limits_raw = raw.get("limits") or {}
    secret_raw = raw.get("secret_scan") or {}
    test_raw = raw.get("test_deletion") or {}
    plan_raw = raw.get("plan_scope") or {}
    return ClosedWorldPolicy(
        schema_version=str(raw.get("schema", "closed_world_policy.v1")),
        mode=str(raw.get("mode", "deny_by_default")),
        limits={
            "max_files_changed": int(limits_raw.get("max_files_changed", 20)),
            "max_diff_lines": int(limits_raw.get("max_diff_lines", 500)),
        },
        always_denied=list(raw.get("always_denied") or []),
        allowed_by_default=list(raw.get("allowed_by_default") or []),
        requires_elevated_approval=_merge_elevated_approval(raw),
        lockfile_globs=list(raw.get("lockfile_globs") or []),
        generated_file_globs=list(raw.get("generated_file_globs") or []),
        secret_scan={"enabled": bool(secret_raw.get("enabled", True))},
        test_deletion={
            "flag_deleted_test_files": bool(test_raw.get("flag_deleted_test_files", True)),
            "flag_assertion_removals": bool(test_raw.get("flag_assertion_removals", True)),
        },
        plan_scope={
            "warn_on_drift": bool(plan_raw.get("warn_on_drift", True)),
            "fail_on_drift": bool(plan_raw.get("fail_on_drift", False)),
        },
        policy_sources=sources,
    )


def _load_project_generated_files(workspace: Path) -> list[str]:
    project_yaml = workspace / ".agent" / "project.yaml"
    if not project_yaml.is_file():
        return []
    try:
        raw = yaml.safe_load(project_yaml.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return []
    state = raw.get("state") or {}
    generated = state.get("generated_files") or []
    return [str(g) for g in generated if g]


def load_closed_world_policy(workspace: Path) -> ClosedWorldPolicy:
    """Load repo policy with platform fallback; merge project generated_files."""
    sources: list[str] = []
    raw: dict[str, Any] | None = None

    repo_policy = workspace / ".agent" / "policies" / "closed_world.yaml"
    if repo_policy.is_file():
        raw = yaml.safe_load(repo_policy.read_text(encoding="utf-8")) or {}
        sources.append(".agent/policies/closed_world.yaml")

    if raw is None and _PLATFORM_DEFAULT.is_file():
        raw = yaml.safe_load(_PLATFORM_DEFAULT.read_text(encoding="utf-8")) or {}
        sources.append("platform_default/closed_world.yml")

    if raw is None:
        raw = {}
        sources.append("platform_default/closed_world.yml")

    policy = _parse_policy_dict(raw, sources)
    extra_generated = _load_project_generated_files(workspace)
    if extra_generated:
        merged = list(policy.generated_file_globs)
        seen = set(merged)
        for g in extra_generated:
            if g not in seen:
                merged.append(g)
                seen.add(g)
        policy = policy.model_copy(update={"generated_file_globs": merged})
    return policy
