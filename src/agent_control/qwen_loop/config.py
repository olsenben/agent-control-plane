"""Load recursive_qwen_loop budget / policy config."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from agent_shared.models.qwen_loop import QwenLoopBudget

_DEFAULT_PATH = Path(__file__).resolve().parents[3] / "config" / "recursive_qwen_loop.yaml"


@lru_cache(maxsize=4)
def load_qwen_loop_config(path: str | None = None) -> dict[str, Any]:
    cfg_path = Path(path) if path else _DEFAULT_PATH
    if not cfg_path.is_file():
        return {"recursive_qwen_loop": {}}
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    return raw if isinstance(raw, dict) else {"recursive_qwen_loop": {}}


def loop_root(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    return (cfg or load_qwen_loop_config()).get("recursive_qwen_loop") or {}


def budget_from_config(cfg: dict[str, Any] | None = None) -> QwenLoopBudget:
    root = loop_root(cfg)
    return QwenLoopBudget(
        max_plan_iterations=int(root.get("max_plan_iterations", 2)),
        max_patch_iterations=int(root.get("max_patch_iterations", 3)),
        max_ci_repair_iterations=int(root.get("max_ci_repair_iterations", 3)),
        max_selected_evidence_refs=int(root.get("max_selected_evidence_refs", 24)),
        max_selected_chars=int(root.get("max_selected_chars", 12000)),
        max_rejected_hypotheses=int(root.get("max_rejected_hypotheses", 10)),
        max_likely_files=int(root.get("max_likely_files", 12)),
    )


def loop_enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(loop_root(cfg).get("enabled", True))


def require_evidence_for_retry(cfg: dict[str, Any] | None = None) -> bool:
    return bool(loop_root(cfg).get("require_evidence_for_retry", True))
