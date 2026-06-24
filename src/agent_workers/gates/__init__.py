"""Closed-world diff gate (Slice 6C)."""

from agent_workers.gates.runner import (
    APPROVED_PATCH_NAME,
    RAW_PATCH_NAME,
    DiffGateError,
    collect_changed_files,
    run_closed_world_diff_gate,
)

__all__ = [
    "APPROVED_PATCH_NAME",
    "RAW_PATCH_NAME",
    "DiffGateError",
    "collect_changed_files",
    "run_closed_world_diff_gate",
]
