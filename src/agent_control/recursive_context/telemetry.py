"""C0/C1 controller telemetry projection (V10 T00.5 gate G2)."""

from __future__ import annotations

from typing import Any

from agent_shared.models.recursive_context import RecursiveContextResult


def controller_telemetry_payload(result: RecursiveContextResult) -> dict[str, Any]:
    """Flat, event-safe proof of which controller arm actually executed."""
    return {
        "recursive_context_required": result.recursive_context_required,
        "recursive_context_invoked": result.invoked,
        "controller_backend": result.controller_backend,
        "controller_mode": result.controller_mode,
        "controller_model_invoked": result.controller_model_invoked,
        "controller_role": result.controller_role,
        "controller_role_label": result.controller_role_label,
        "controller_model_id": result.controller_model_id,
        "controller_provider": result.controller_provider,
        "controller_attempts": result.controller_attempts,
        "controller_prompt_tokens": result.controller_prompt_tokens,
        "controller_completion_tokens": result.controller_completion_tokens,
        "controller_wall_seconds": result.controller_wall_seconds,
        "controller_gpu_seconds": result.controller_gpu_seconds,
        "controller_data_left_homelab": result.controller_data_left_homelab,
        "controller_error_class": result.controller_error_class,
        "invocation_reasons": list(result.invocation_reasons),
        "stop_reason": result.stop_reason,
    }
