"""Typed ACI tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_control.sandbox.command_runner import run_registered_command


def list_tree(root: Path, max_depth: int = 3) -> list[str]:
    paths: list[str] = []
    root = root.resolve()
    for path in root.rglob("*"):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            if rel.count("/") <= max_depth:
                paths.append(rel)
    return sorted(paths)[:500]


def read_file(path: Path, max_bytes: int = 20000) -> str:
    data = path.read_bytes()[:max_bytes]
    return data.decode("utf-8", errors="replace")


def run_command(command_id: str, cwd: Path | None = None) -> dict[str, Any]:
    """ACI adapter: command IDs only, via shared command_runner (SandboxBackend)."""
    if cwd is None:
        return {
            "command_id": command_id,
            "status": "error",
            "violated": True,
            "violation_codes": ["workspace_required"],
        }
    result = run_registered_command(command_id, workspace=cwd)
    return {
        "command_id": command_id,
        "status": "ok" if result.exit_code == 0 and not result.violated else "failed",
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "violated": result.violated,
        "violation_codes": result.violation_codes,
        "session_id": result.session_id,
        "backend": result.backend,
        "attestation_mode": result.attestation.mode if result.attestation else None,
        "cwd": str(cwd),
    }
