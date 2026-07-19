"""tool_policy.v2 — narrowing-only repo command policy from pinned workspace.

Missing, invalid, unsupported-version, or unreadable tools.yaml yields an empty
repository allowance (no command execution). Repos may only list central command
IDs and tighten constraints; they must not supply argv, executables, env, cwd,
shell, network beyond allow_network, credentials, or new command IDs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

from agent_shared.hash_utils import canonical_json_hash

TOOL_POLICY_SCHEMA = "tool_policy.v2"
TOOLS_RELATIVE_PATH = ".agent/policies/tools.yaml"
HASH_ALGORITHM = "sha256"

_ALLOWED_TOP_KEYS = frozenset(
    {
        "schema",
        "allowed_command_ids",
        "constraints",
        "deny_freeform_shell",
        "allow_network",
    }
)
_ALLOWED_CONSTRAINT_KEYS = frozenset({"allowed_path_globs", "max_timeout_seconds"})
_REJECT_COMMAND_KEYS = frozenset(
    {
        "argv",
        "executable",
        "argv_template",
        "shell",
        "env",
        "environment",
        "environment_allowlist",
        "cwd",
        "network",
        "network_required",
        "credentials",
        "credential",
        "api_key",
        "token",
    }
)

ToolPolicyStatus = Literal["ok", "empty_missing", "empty_invalid", "empty_unsupported"]


@dataclass(frozen=True)
class CommandConstraint:
    allowed_path_globs: tuple[str, ...] = ()
    max_timeout_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.allowed_path_globs:
            out["allowed_path_globs"] = list(self.allowed_path_globs)
        if self.max_timeout_seconds is not None:
            out["max_timeout_seconds"] = self.max_timeout_seconds
        return out


@dataclass
class ToolPolicyLoadResult:
    status: ToolPolicyStatus
    allowed_command_ids: list[str] = field(default_factory=list)
    constraints: dict[str, CommandConstraint] = field(default_factory=dict)
    deny_freeform_shell: bool = True
    allow_network: bool = False
    warnings: list[str] = field(default_factory=list)
    command_registry_hash: str = ""
    effective_command_policy_hash: str = ""
    hash_algorithm: str = HASH_ALGORITHM
    loaded_path: str | None = None

    @property
    def execution_allowed(self) -> bool:
        return self.status == "ok" and bool(self.allowed_command_ids)


def hash_command_registry(registry: dict[str, Any]) -> str:
    """Full central registry hash (canonical JSON, sha256)."""
    payload = {
        "hash_schema": "command_registry_hash.v1",
        "hash_algorithm": HASH_ALGORITHM,
        "registry": registry,
    }
    return canonical_json_hash(payload)


def hash_effective_command_policy(
    *,
    allowed_command_ids: list[str],
    constraints: dict[str, CommandConstraint],
    deny_freeform_shell: bool,
    allow_network: bool,
    command_registry_hash: str,
) -> str:
    """Effective command-policy hash after intersection with the central registry."""
    constraint_map = {
        cid: constraints[cid].to_dict()
        for cid in sorted(constraints)
        if cid in set(allowed_command_ids)
    }
    payload = {
        "hash_schema": "effective_command_policy_hash.v1",
        "hash_algorithm": HASH_ALGORITHM,
        "tool_policy_schema": TOOL_POLICY_SCHEMA,
        "command_registry_hash": command_registry_hash,
        "allowed_command_ids": list(allowed_command_ids),
        "constraints": constraint_map,
        "deny_freeform_shell": deny_freeform_shell,
        "allow_network": allow_network,
    }
    return canonical_json_hash(payload)


def _empty_result(
    status: ToolPolicyStatus,
    *,
    registry: dict[str, Any],
    warnings: list[str],
    loaded_path: str | None = None,
) -> ToolPolicyLoadResult:
    reg_hash = hash_command_registry(registry)
    eff_hash = hash_effective_command_policy(
        allowed_command_ids=[],
        constraints={},
        deny_freeform_shell=True,
        allow_network=False,
        command_registry_hash=reg_hash,
    )
    return ToolPolicyLoadResult(
        status=status,
        allowed_command_ids=[],
        constraints={},
        deny_freeform_shell=True,
        allow_network=False,
        warnings=list(warnings),
        command_registry_hash=reg_hash,
        effective_command_policy_hash=eff_hash,
        loaded_path=loaded_path,
    )


def validate_path_glob(pattern: str) -> str:
    """Normalize a relative path glob; reject escapes and absolute paths."""
    if not isinstance(pattern, str) or not pattern.strip():
        raise ValueError("path_glob_empty")
    raw = pattern.replace("\\", "/").strip()
    if raw.startswith("/") or (len(raw) > 1 and raw[1] == ":"):
        raise ValueError("path_glob_absolute")
    parts = [p for p in raw.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise ValueError("path_glob_parent_escape")
    if any(p.startswith("~") for p in parts):
        raise ValueError("path_glob_home")
    # Reject NUL and control chars
    if any(ord(c) < 32 for c in raw):
        raise ValueError("path_glob_control_char")
    return "/".join(parts) if parts else raw


def _parse_constraints(
    raw: Any,
    *,
    allowed_ids: set[str],
    central_timeouts: dict[str, float],
) -> dict[str, CommandConstraint]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("constraints_not_object")
    out: dict[str, CommandConstraint] = {}
    for cid, spec in raw.items():
        if not isinstance(cid, str):
            raise ValueError("constraint_id_not_string")
        if cid not in allowed_ids:
            raise ValueError(f"constraint_unknown_command_id:{cid}")
        if not isinstance(spec, dict):
            raise ValueError(f"constraint_not_object:{cid}")
        unknown = set(spec) - _ALLOWED_CONSTRAINT_KEYS
        if unknown:
            raise ValueError(f"constraint_unknown_keys:{cid}:{sorted(unknown)}")
        forbidden = set(spec) & _REJECT_COMMAND_KEYS
        if forbidden:
            raise ValueError(f"constraint_forbidden_keys:{cid}:{sorted(forbidden)}")
        globs_raw = spec.get("allowed_path_globs")
        globs: list[str] = []
        if globs_raw is not None:
            if not isinstance(globs_raw, list) or not all(isinstance(g, str) for g in globs_raw):
                raise ValueError(f"constraint_globs_invalid:{cid}")
            globs = [validate_path_glob(g) for g in globs_raw]
        max_to = spec.get("max_timeout_seconds")
        timeout: float | None = None
        if max_to is not None:
            if not isinstance(max_to, (int, float)) or isinstance(max_to, bool):
                raise ValueError(f"constraint_timeout_invalid:{cid}")
            timeout = float(max_to)
            if timeout <= 0:
                raise ValueError(f"constraint_timeout_nonpositive:{cid}")
            central = central_timeouts.get(cid)
            if central is not None and timeout > central:
                raise ValueError(f"constraint_timeout_exceeds_central:{cid}")
        out[cid] = CommandConstraint(
            allowed_path_globs=tuple(globs),
            max_timeout_seconds=timeout,
        )
    return out


def parse_tool_policy_v2(
    data: Any,
    *,
    registry: dict[str, Any],
) -> ToolPolicyLoadResult:
    """Parse already-loaded YAML/JSON. Invalid → empty allowance."""
    warnings: list[str] = []
    if not isinstance(data, dict):
        return _empty_result("empty_invalid", registry=registry, warnings=["tools_yaml_not_object"])

    schema = data.get("schema")
    if schema != TOOL_POLICY_SCHEMA:
        status: ToolPolicyStatus = (
            "empty_unsupported" if isinstance(schema, str) and schema else "empty_invalid"
        )
        return _empty_result(
            status,
            registry=registry,
            warnings=[f"tools_yaml_schema:{schema!r}"],
        )

    unknown_top = set(data) - _ALLOWED_TOP_KEYS
    if unknown_top:
        return _empty_result(
            "empty_invalid",
            registry=registry,
            warnings=[f"tools_yaml_unknown_keys:{sorted(unknown_top)}"],
        )

    # Reject legacy v1-style nested command definitions
    if "commands" in data:
        return _empty_result(
            "empty_invalid",
            registry=registry,
            warnings=["tools_yaml_commands_block_forbidden"],
        )

    ids_raw = data.get("allowed_command_ids")
    if ids_raw is None:
        return _empty_result(
            "empty_invalid",
            registry=registry,
            warnings=["tools_yaml_missing_allowed_command_ids"],
        )
    if not isinstance(ids_raw, list) or not all(isinstance(x, str) and x.strip() for x in ids_raw):
        return _empty_result(
            "empty_invalid",
            registry=registry,
            warnings=["tools_yaml_allowed_command_ids_invalid"],
        )

    central_commands = data_registry_commands(registry)
    central_timeouts = {
        cid: float((spec or {}).get("timeout_seconds", 120))
        for cid, spec in central_commands.items()
        if isinstance(spec, dict)
    }
    allowed: list[str] = []
    seen: set[str] = set()
    for cid in ids_raw:
        name = cid.strip()
        if name in seen:
            continue
        if name not in central_commands:
            return _empty_result(
                "empty_invalid",
                registry=registry,
                warnings=[f"tools_yaml_unknown_command_id:{name}"],
            )
        seen.add(name)
        allowed.append(name)

    deny_shell = data.get("deny_freeform_shell", True)
    allow_net = data.get("allow_network", False)
    if not isinstance(deny_shell, bool) or not isinstance(allow_net, bool):
        return _empty_result(
            "empty_invalid",
            registry=registry,
            warnings=["tools_yaml_bool_fields_invalid"],
        )
    if allow_net:
        # Network enablement is not repo-grantable in v2 closeout; treat as invalid.
        return _empty_result(
            "empty_invalid",
            registry=registry,
            warnings=["tools_yaml_allow_network_forbidden"],
        )

    try:
        constraints = _parse_constraints(
            data.get("constraints"),
            allowed_ids=set(allowed),
            central_timeouts=central_timeouts,
        )
    except ValueError as exc:
        return _empty_result(
            "empty_invalid",
            registry=registry,
            warnings=[f"tools_yaml_constraints:{exc}"],
        )

    reg_hash = hash_command_registry(registry)
    # Intersection: only IDs present in both repo allowlist and registry (already filtered)
    eff_hash = hash_effective_command_policy(
        allowed_command_ids=allowed,
        constraints=constraints,
        deny_freeform_shell=deny_shell,
        allow_network=False,
        command_registry_hash=reg_hash,
    )
    if not allowed:
        warnings.append("tools_yaml_empty_allowlist")
        return ToolPolicyLoadResult(
            status="ok",
            allowed_command_ids=[],
            constraints={},
            deny_freeform_shell=deny_shell,
            allow_network=False,
            warnings=warnings,
            command_registry_hash=reg_hash,
            effective_command_policy_hash=eff_hash,
        )
    return ToolPolicyLoadResult(
        status="ok",
        allowed_command_ids=allowed,
        constraints=constraints,
        deny_freeform_shell=deny_shell,
        allow_network=False,
        warnings=warnings,
        command_registry_hash=reg_hash,
        effective_command_policy_hash=eff_hash,
    )


def data_registry_commands(registry: dict[str, Any]) -> dict[str, Any]:
    commands = registry.get("commands") or {}
    return commands if isinstance(commands, dict) else {}


def load_tool_policy_from_text(
    text: str | None,
    *,
    registry: dict[str, Any] | None = None,
    registry_path: Path | None = None,
    loaded_path: str | None = None,
) -> ToolPolicyLoadResult:
    from agent_control.sandbox.command_runner import load_command_registry

    reg = registry if registry is not None else load_command_registry(registry_path)
    if text is None:
        return _empty_result("empty_missing", registry=reg, warnings=["tools_yaml_missing"])
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return _empty_result(
            "empty_invalid",
            registry=reg,
            warnings=[f"tools_yaml_parse_error:{exc}"],
            loaded_path=loaded_path,
        )
    result = parse_tool_policy_v2(data, registry=reg)
    result.loaded_path = loaded_path
    return result


def load_tool_policy_from_workspace(
    policy_workspace: Path,
    *,
    registry: dict[str, Any] | None = None,
    registry_path: Path | None = None,
) -> ToolPolicyLoadResult:
    """Load tools.yaml only from the pinned policy workspace tree."""
    from agent_control.sandbox.command_runner import default_registry_path, load_command_registry

    reg = registry if registry is not None else load_command_registry(registry_path or default_registry_path())
    path = policy_workspace / TOOLS_RELATIVE_PATH
    if not path.is_file():
        return _empty_result(
            "empty_missing",
            registry=reg,
            warnings=["tools_yaml_missing"],
            loaded_path=TOOLS_RELATIVE_PATH,
        )
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return _empty_result(
            "empty_invalid",
            registry=reg,
            warnings=[f"tools_yaml_unreadable:{exc}"],
            loaded_path=TOOLS_RELATIVE_PATH,
        )
    return load_tool_policy_from_text(
        text,
        registry=reg,
        loaded_path=TOOLS_RELATIVE_PATH,
    )


def intersect_command_ids(
    requested: list[str],
    allowed: list[str],
) -> list[str]:
    allow = set(allowed)
    return [cid for cid in requested if cid in allow]


def effective_timeout_seconds(
    command_id: str,
    central_timeout: float,
    constraints: dict[str, CommandConstraint],
) -> float:
    constraint = constraints.get(command_id)
    if constraint is None or constraint.max_timeout_seconds is None:
        return central_timeout
    return min(central_timeout, float(constraint.max_timeout_seconds))
