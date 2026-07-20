"""Load experiment flags (patch tournaments / rewards). Defaults off."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "experiments.yaml"


@lru_cache(maxsize=4)
def load_experiments_config(path: str | None = None) -> dict[str, Any]:
    cfg_path = Path(path) if path else _DEFAULT_PATH
    if not cfg_path.is_file():
        return {
            "experiments": {
                "patch_tournament": False,
                "rl_reward_logging": False,
                "max_tournament_candidates": 4,
            }
        }
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    return raw if isinstance(raw, dict) else {"experiments": {}}


def experiments_root(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    return (cfg or load_experiments_config()).get("experiments") or {}


def patch_tournament_enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(experiments_root(cfg).get("patch_tournament", False))


def reward_logging_enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(experiments_root(cfg).get("rl_reward_logging", False))


def max_tournament_candidates(cfg: dict[str, Any] | None = None) -> int:
    return int(experiments_root(cfg).get("max_tournament_candidates", 4))
