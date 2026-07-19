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
    allowed_command_ids: list[str] | None = None,
    command_constraints: dict[str, Any] | None = None,
    expected_effective_command_policy_hash: str | None = None,
    effective_command_policy_hash: str | None = None,
) -> dict[str, Any]:
    """Run required registered command IDs (not freeform shell).

    ``commands`` must be registry IDs. If empty and ``failure_class`` is set,
    IDs are taken from ``failure_class_commands`` in the deployed registry.
    When ``allowed_command_ids`` is provided, IDs are intersected (empty → blocked).
    """
    del patch_path  # patch already applied to workspace before verify
    settings = settings or get_settings()
    if (
        expected_effective_command_policy_hash
        and effective_command_policy_hash
        and expected_effective_command_policy_hash != effective_command_policy_hash
    ):
        return {
            "schema_version": "verification_result.v1",
            "status": "blocked",
            "passed": False,
            "message": "effective_command_policy_hash_mismatch",
            "commands": [],
            "sandbox": {"network": False, "secrets_mounted": False, "destroyed": True},
        }

    command_ids = list(commands)
    if not command_ids and failure_class:
        command_ids = required_command_ids_for_failure_class(failure_class)
    if allowed_command_ids is not None:
        from agent_control.sandbox.tool_policy import intersect_command_ids

        command_ids = intersect_command_ids(command_ids, list(allowed_command_ids))
    if not command_ids:
        return {
            "schema_version": "verification_result.v1",
            "status": "blocked",
            "passed": False,
            "message": "no_mapped_verifier" if allowed_command_ids is None else "tool_policy_empty_allowance",
            "commands": [],
            "sandbox": {"network": False, "secrets_mounted": False, "destroyed": True},
        }

    results = run_required_verifiers(
        command_ids,
        workspace=workspace,
        settings=settings,
        allowed_command_ids=allowed_command_ids,
        command_constraints=command_constraints,
    )
    passed = all(r.exit_code == 0 and not r.violated for r in results)
    status = "passed" if passed else "failed"
    if any("sandbox_check_failed" in r.violation_codes for r in results):
        status = "sandbox_failed"
    if any("tool_policy_rejected" in r.violation_codes for r in results):
        status = "blocked"
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
