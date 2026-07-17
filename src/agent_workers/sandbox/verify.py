"""Verification via deployed command registry + SandboxBackend (Slice 5.8)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_control.config import Settings, get_settings
from agent_control.sandbox.command_runner import (
    required_command_ids_for_failure_class,
    run_required_verifiers,
)


def run_verification_sandbox(
    patch_path: Path,
    workspace: Path,
    commands: list[str],
    *,
    failure_class: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Run required registered command IDs (not freeform shell).

    ``commands`` must be registry IDs. If empty and ``failure_class`` is set,
    IDs are taken from ``failure_class_commands`` in the deployed registry.
    """
    del patch_path  # patch already applied to workspace before verify
    settings = settings or get_settings()
    command_ids = list(commands)
    if not command_ids and failure_class:
        command_ids = required_command_ids_for_failure_class(failure_class)
    if not command_ids:
        return {
            "schema_version": "verification_result.v1",
            "status": "blocked",
            "passed": False,
            "message": "no_mapped_verifier",
            "commands": [],
            "sandbox": {"network": False, "secrets_mounted": False, "destroyed": True},
        }

    results = run_required_verifiers(command_ids, workspace=workspace, settings=settings)
    passed = all(r.exit_code == 0 and not r.violated for r in results)
    status = "passed" if passed else "failed"
    if any("sandbox_check_failed" in r.violation_codes for r in results):
        status = "sandbox_failed"
    return {
        "schema_version": "verification_result.v1",
        "status": status,
        "passed": passed,
        "message": "ok" if passed else "verification_failed",
        "commands": [r.to_dict() for r in results],
        "sandbox": {
            "network": False,
            "secrets_mounted": False,
            "destroyed": True,
            "session_id": results[0].session_id if results else None,
            "backend": results[0].backend if results else None,
        },
    }
