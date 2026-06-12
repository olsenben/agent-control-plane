"""Prompt and context budget helpers for RLM engines."""

from __future__ import annotations

from typing import Any


def job_limits(job: dict[str, Any]) -> dict[str, Any]:
    return job.get("limits") or {}


def capped_iterations(job: dict[str, Any], strategy_cap: int) -> int:
    requested = int(job_limits(job).get("max_iterations", strategy_cap))
    return max(1, min(requested, strategy_cap))


def capped_depth(job: dict[str, Any], strategy_cap: int) -> int:
    requested = int(job_limits(job).get("max_depth", strategy_cap))
    return max(0, min(requested, strategy_cap))


def truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20] + "\n...[truncated]"
