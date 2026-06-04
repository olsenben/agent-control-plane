"""Deterministic context capsule builder (stub)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_control.state_reducer import LogicalState


def build_context_capsule(state: LogicalState, repo_path: Path | None = None) -> dict[str, Any]:
    return {
        "schema": "agent.state_manifest.v1",
        "project": state.project,
        "head_sha": state.head_sha,
        "reduction_mode": state.reduction_mode.value,
        "command_intent": state.command_intent,
        "context_overflow": False,
        "repo_path": str(repo_path) if repo_path else None,
    }
