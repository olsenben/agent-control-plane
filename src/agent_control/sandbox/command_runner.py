"""Trusted registered-command execution (Slice 5.8).

Loaded only from the deployed ACP installation — never from a target checkout.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from agent_control.aci.backends.base import CommandResult, SandboxAttestation
from agent_control.aci.backends.srt import get_sandbox_backend
from agent_control.config import Settings, get_settings

logger = logging.getLogger(__name__)

_FORBIDDEN_ENV_KEYS = frozenset(
    {
        "GITEA_BOT_TOKEN",
        "GITEA_AGENT_TOKEN",
        "GITEA_WEBHOOK_SECRET",
        "REDIS_URL",
        "MODEL_3080_API_KEY",
        "MODEL_2070_API_KEY",
    }
)


@dataclass
class RegisteredCommand:
    command_id: str
    argv: list[str]
    cwd: str = "repo_root"
    timeout_seconds: float = 120.0
    environment_allowlist: list[str] = field(default_factory=lambda: ["PATH", "HOME"])
    max_output_bytes: int = 1_048_576


@dataclass
class RegisteredCommandResult:
    command_id: str
    exit_code: int
    stdout: str
    stderr: str
    violated: bool = False
    violation_codes: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    attestation: SandboxAttestation | None = None
    session_id: str = ""
    backend: str = ""
    output_artifact_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "command_id": self.command_id,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "violated": self.violated,
            "violation_codes": list(self.violation_codes),
            "duration_seconds": self.duration_seconds,
            "session_id": self.session_id,
            "backend": self.backend,
            "attestation_mode": self.attestation.mode if self.attestation else None,
            "attestation_strong_ok": self.attestation.strong_ok if self.attestation else False,
            "attestation_checked_at": self.attestation.checked_at if self.attestation else None,
            "output_artifact_ref": self.output_artifact_ref,
        }


def default_registry_path() -> Path:
    env = os.environ.get("COMMAND_REGISTRY_PATH", "").strip()
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    candidates = [
        here.parents[3] / "config" / "command_registry.yaml",
        Path("/opt/ai-sdlc-lab/agent-control-plane/config/command_registry.yaml"),
        Path.cwd() / "config" / "command_registry.yaml",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return candidates[0]


def load_command_registry(path: Path | None = None) -> dict[str, Any]:
    registry_path = path or default_registry_path()
    if not registry_path.is_file():
        raise FileNotFoundError(f"command_registry_missing:{registry_path}")
    data = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("command_registry_invalid_root")
    return data


def get_registered_command(
    command_id: str,
    *,
    registry: dict[str, Any] | None = None,
    registry_path: Path | None = None,
) -> RegisteredCommand:
    data = registry if registry is not None else load_command_registry(registry_path)
    commands = data.get("commands") or {}
    if command_id not in commands:
        raise KeyError(f"unknown_command_id:{command_id}")
    raw = commands[command_id]
    if not isinstance(raw, dict):
        raise ValueError(f"command_spec_invalid:{command_id}")
    argv = raw.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv):
        raise ValueError(f"command_argv_invalid:{command_id}")
    for a in argv:
        if any(m in a for m in ("|", ";", "&&", "||", "`", "$(", ">", "<")):
            raise ValueError(f"command_argv_shell_meta:{command_id}")
    allow = raw.get("environment_allowlist") or ["PATH", "HOME"]
    if not isinstance(allow, list) or not all(isinstance(x, str) for x in allow):
        raise ValueError(f"command_env_allowlist_invalid:{command_id}")
    timeout = float(raw.get("timeout_seconds", 120))
    if timeout <= 0 or timeout > 3600:
        raise ValueError(f"command_timeout_invalid:{command_id}")
    max_out = int(raw.get("max_output_bytes", 1_048_576))
    return RegisteredCommand(
        command_id=command_id,
        argv=list(argv),
        cwd=str(raw.get("cwd") or "repo_root"),
        timeout_seconds=timeout,
        environment_allowlist=list(allow),
        max_output_bytes=max_out,
    )


def required_command_ids_for_failure_class(
    failure_class: str,
    *,
    registry: dict[str, Any] | None = None,
    registry_path: Path | None = None,
) -> list[str]:
    data = registry if registry is not None else load_command_registry(registry_path)
    mapping = data.get("failure_class_commands") or {}
    ids = mapping.get(failure_class) or []
    if not isinstance(ids, list):
        return []
    return [str(x) for x in ids]


def _resolve_cwd(workspace: Path, cwd_token: str) -> Path:
    workspace = workspace.resolve()
    if cwd_token in ("repo_root", ".", ""):
        return workspace
    candidate = (workspace / cwd_token).resolve()
    try:
        candidate.relative_to(workspace)
    except ValueError as exc:
        raise ValueError("cwd_outside_workspace") from exc
    if candidate.is_symlink():
        raise ValueError("cwd_symlink_rejected")
    if not candidate.is_dir():
        raise ValueError("cwd_not_directory")
    return candidate


def _build_clean_env(allowlist: list[str]) -> dict[str, str]:
    env: dict[str, str] = {}
    for key in allowlist:
        if key in _FORBIDDEN_ENV_KEYS or key.startswith("GITEA_"):
            continue
        if key in ("PATH", "HOME", "LANG", "LC_ALL", "PYTHONPATH", "TMPDIR", "TEMP", "TMP"):
            val = os.environ.get(key)
            if val is not None:
                env[key] = val
    for bad in list(env):
        if bad in _FORBIDDEN_ENV_KEYS or bad.startswith("GITEA_"):
            env.pop(bad, None)
    if "PATH" not in env:
        env["PATH"] = os.environ.get("PATH", "/usr/bin:/bin")
    return env


def _truncate(text: str, max_bytes: int) -> str:
    raw = text.encode("utf-8", errors="replace")
    if len(raw) <= max_bytes:
        return text
    return raw[:max_bytes].decode("utf-8", errors="replace") + "\n...[truncated]"


def run_registered_command(
    command_id: str,
    *,
    workspace: Path,
    settings: Settings | None = None,
    registry_path: Path | None = None,
    extra_argv: list[str] | None = None,
    session_id: str | None = None,
    allowed_command_ids: list[str] | frozenset[str] | set[str] | None = None,
    command_constraints: dict[str, Any] | None = None,
) -> RegisteredCommandResult:
    """Resolve trusted argv and execute only through SandboxBackend (no shell, no fallback).

    When ``allowed_command_ids`` is provided (including empty), the ID must be in that
    set — empty means deny all (tool_policy.v2 fail-closed). ``None`` skips the
    repo-policy gate (central registry only; used by unit tests).
    """
    if extra_argv:
        raise ValueError("caller_argv_forbidden")

    settings = settings or get_settings()
    session = session_id or str(uuid.uuid4())
    started = time.monotonic()

    if allowed_command_ids is not None and command_id not in set(allowed_command_ids):
        return RegisteredCommandResult(
            command_id=command_id,
            exit_code=126,
            stdout="",
            stderr="tool_policy_command_denied",
            violated=True,
            violation_codes=["tool_policy_rejected"],
            duration_seconds=time.monotonic() - started,
            session_id=session,
            backend="none",
        )

    try:
        spec = get_registered_command(command_id, registry_path=registry_path)
        if command_constraints and command_id in command_constraints:
            from agent_control.sandbox.tool_policy import (
                CommandConstraint,
                effective_timeout_seconds,
            )

            raw_c = command_constraints[command_id] or {}
            constraint = CommandConstraint(
                allowed_path_globs=tuple(raw_c.get("allowed_path_globs") or ()),
                max_timeout_seconds=(
                    float(raw_c["max_timeout_seconds"])
                    if raw_c.get("max_timeout_seconds") is not None
                    else None
                ),
            )
            narrowed = effective_timeout_seconds(
                command_id, spec.timeout_seconds, {command_id: constraint}
            )
            spec = RegisteredCommand(
                command_id=spec.command_id,
                argv=list(spec.argv),
                cwd=spec.cwd,
                timeout_seconds=narrowed,
                environment_allowlist=list(spec.environment_allowlist),
                max_output_bytes=spec.max_output_bytes,
            )
        cwd = _resolve_cwd(workspace, spec.cwd)
    except (KeyError, ValueError, FileNotFoundError) as exc:
        return RegisteredCommandResult(
            command_id=command_id,
            exit_code=126,
            stdout="",
            stderr=str(exc),
            violated=True,
            violation_codes=["registry_rejected"],
            duration_seconds=time.monotonic() - started,
            session_id=session,
            backend="none",
        )

    backend = get_sandbox_backend(
        settings.sandbox_backend,
        expected_policy_hash=settings.sandbox_expected_policy_hash or None,
    )
    policy = settings.sandbox_expected_policy_hash or ""
    attestation = backend.attest(workspace=workspace, policy_hash=policy)
    if not attestation.strong_ok:
        logger.warning(
            "sandbox_check_failed command_id=%s session=%s mode=%s",
            command_id,
            session,
            attestation.mode,
        )
        return RegisteredCommandResult(
            command_id=command_id,
            exit_code=126,
            stdout="",
            stderr="sandbox_attestation_failed",
            violated=True,
            violation_codes=["sandbox_check_failed"],
            duration_seconds=time.monotonic() - started,
            attestation=attestation,
            session_id=session,
            backend=backend.name,
        )

    env = _build_clean_env(spec.environment_allowlist)
    result: CommandResult = backend.run(
        list(spec.argv),
        cwd=cwd,
        workspace=workspace.resolve(),
        timeout_seconds=spec.timeout_seconds,
        env=env,
    )
    return RegisteredCommandResult(
        command_id=command_id,
        exit_code=result.exit_code,
        stdout=_truncate(result.stdout, spec.max_output_bytes),
        stderr=_truncate(result.stderr, spec.max_output_bytes),
        violated=result.violated,
        violation_codes=list(result.violation_codes),
        duration_seconds=time.monotonic() - started,
        attestation=attestation,
        session_id=session,
        backend=backend.name,
    )


def run_required_verifiers(
    command_ids: list[str],
    *,
    workspace: Path,
    settings: Settings | None = None,
    registry_path: Path | None = None,
    session_id: str | None = None,
    allowed_command_ids: list[str] | frozenset[str] | set[str] | None = None,
    command_constraints: dict[str, Any] | None = None,
) -> list[RegisteredCommandResult]:
    session = session_id or str(uuid.uuid4())
    results: list[RegisteredCommandResult] = []
    for cid in command_ids:
        results.append(
            run_registered_command(
                cid,
                workspace=workspace,
                settings=settings,
                registry_path=registry_path,
                session_id=session,
                allowed_command_ids=allowed_command_ids,
                command_constraints=command_constraints,
            )
        )
        if results[-1].violated or results[-1].exit_code != 0:
            break
    return results
