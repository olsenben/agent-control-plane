"""Deterministic fast-verifier selection (VExp W2-B)."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from agent_shared.models.fast_verification import VerifierSelection

DEV_FAST_VERIFY_TIMEOUT_S = 120
DEFAULT_OUTPUT_LIMIT_BYTES = 1_048_576


def select_fast_verifier(
    *,
    task: Mapping[str, Any] | None = None,
    snapshot_sha: str = "",
    verification_binding: Mapping[str, Any] | None = None,
    official_commands: Sequence[str] | None = None,
    source: str = "eval_manifest",
) -> VerifierSelection | None:
    """Select one bounded fast verifier binding. Model never supplies commands."""
    binding = verification_binding or {}
    commands = list(official_commands or binding.get("official_commands") or [])
    if not commands and task:
        commands = list(task.get("official_commands") or [])
    if not commands:
        return None

    command_ref = str(commands[0])
    verifier_id = "eval:official[0]" if source == "eval_manifest" else f"registry:{command_ref}"

    return VerifierSelection(
        verifier_id=verifier_id,
        source="eval_manifest" if source == "eval_manifest" else "registry",
        command_ref=command_ref,
        display_name=f"official[0]: {command_ref[:80]}",
        timeout_s=int(binding.get("timeout_s") or DEV_FAST_VERIFY_TIMEOUT_S),
        output_limit_bytes=int(binding.get("output_limit_bytes") or DEFAULT_OUTPUT_LIMIT_BYTES),
    )


def select_registry_verifier(
    *,
    command_id: str,
    display_name: str | None = None,
    timeout_s: int = DEV_FAST_VERIFY_TIMEOUT_S,
) -> VerifierSelection:
    """Production registry-ID selection."""
    return VerifierSelection(
        verifier_id=f"registry:{command_id}",
        source="registry",
        command_ref=command_id,
        display_name=display_name or command_id,
        timeout_s=timeout_s,
    )
