"""Load recursive_context budget / policy config."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from agent_shared.models.recursive_context import RecursiveContextBudget

_DEFAULT_PATH = Path(__file__).resolve().parents[3] / "config" / "recursive_context.yaml"


@lru_cache(maxsize=4)
def load_recursive_context_config(path: str | None = None) -> dict[str, Any]:
    cfg_path = Path(path) if path else _DEFAULT_PATH
    if not cfg_path.is_file():
        return {"recursive_context": {}}
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    return raw if isinstance(raw, dict) else {"recursive_context": {}}


def budget_from_config(cfg: dict[str, Any] | None = None) -> RecursiveContextBudget:
    root = (cfg or load_recursive_context_config()).get("recursive_context") or {}
    return RecursiveContextBudget(
        max_depth=int(root.get("max_depth", 2)),
        max_subcalls=int(root.get("max_subcalls", 6)),
        max_graph_queries=int(root.get("max_graph_queries", 20)),
        max_memory_records=int(root.get("max_memory_records", 24)),
        max_wall_seconds=int(root.get("max_wall_seconds", 180)),
        max_prompt_tokens_per_subcall=int(root.get("max_prompt_tokens_per_subcall", 8192)),
        max_total_input_tokens=int(root.get("max_total_input_tokens", 60000)),
        max_total_output_tokens=int(root.get("max_total_output_tokens", 12000)),
        output_max_chars=int(root.get("output_max_chars", 16000)),
    )


def allowed_tools(cfg: dict[str, Any] | None = None) -> frozenset[str]:
    root = (cfg or load_recursive_context_config()).get("recursive_context") or {}
    tools = root.get("allowed_tools") or []
    return frozenset(str(t) for t in tools)
