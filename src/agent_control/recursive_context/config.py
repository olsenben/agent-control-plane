"""Load recursive_context budget / policy config."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from agent_shared.models.recursive_context import ControllerBackend, RecursiveContextBudget

_DEFAULT_PATH = Path(__file__).resolve().parents[3] / "config" / "recursive_context.yaml"

CONTROLLER_BACKENDS: frozenset[str] = frozenset({"deterministic", "model"})
DEFAULT_CONTROLLER_BACKEND: ControllerBackend = "deterministic"


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


def resolve_controller_backend(
    cfg: dict[str, Any] | None = None,
    *,
    settings: Any | None = None,
    override: str | None = None,
) -> ControllerBackend:
    """Pick the V10 T00.5 controller arm.

    Precedence: explicit CLI/caller override, then
    ``RECURSIVE_CONTEXT_CONTROLLER_BACKEND``, then the yaml pin. Anything
    unrecognised falls back to ``deterministic`` so the production arm can never
    be switched on by a typo.
    """
    root = (cfg or load_recursive_context_config()).get("recursive_context") or {}
    if settings is None:
        from agent_control.config import get_settings

        settings = get_settings()
    candidates = (
        override,
        getattr(settings, "recursive_context_controller_backend", ""),
        root.get("controller_backend"),
    )
    for candidate in candidates:
        value = str(candidate or "").strip().lower()
        if value in CONTROLLER_BACKENDS:
            return value  # type: ignore[return-value]
    return DEFAULT_CONTROLLER_BACKEND


def controller_roles(cfg: dict[str, Any] | None = None) -> tuple[str, str]:
    """Return (gateway_role, policy_role_label) for the recursive controller."""
    root = (cfg or load_recursive_context_config()).get("recursive_context") or {}
    gateway_role = str(root.get("primary_model_role") or "summarizer").strip()
    label = str(root.get("controller_role") or "gpu-2070").strip()
    return gateway_role, label


def allowed_tools(cfg: dict[str, Any] | None = None) -> frozenset[str]:
    root = (cfg or load_recursive_context_config()).get("recursive_context") or {}
    tools = root.get("allowed_tools") or []
    return frozenset(str(t) for t in tools)
