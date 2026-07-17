"""Sandbox execution services (Slice 5.8)."""

from agent_control.sandbox.command_runner import (
    RegisteredCommandResult,
    required_command_ids_for_failure_class,
    run_registered_command,
    run_required_verifiers,
)

__all__ = [
    "RegisteredCommandResult",
    "required_command_ids_for_failure_class",
    "run_registered_command",
    "run_required_verifiers",
]
