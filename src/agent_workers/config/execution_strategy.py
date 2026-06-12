"""Platform-owned execution_strategy configuration (V1)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from agent_workers.rlm.constants import ENGINE_FAKE, ENGINE_MINIMAL, ENGINE_OFFICIAL

DEFAULT_STRATEGY_PATH = (
    Path(__file__).resolve().parent / "platform_default" / "execution_strategy.yml"
)

ENGINE_NAME_TO_POLICY_KEY = {
    ENGINE_FAKE: "fake",
    ENGINE_MINIMAL: "local",
    ENGINE_OFFICIAL: "official",
}


@dataclass(frozen=True)
class ExecutionStrategy:
    schema_version: str
    default_engine: str
    fallback_engine: str
    test_engine: str
    model_policy_map: dict[str, str]
    read_only_max_prompt_chars: int = 12000
    read_only_max_context_files: int = 5
    rlms_max_iterations_cap: int = 3
    rlms_max_depth_cap: int = 0
    external_agent_backends_mode: str = "rlm_tool_only"
    external_agent_backends_allowed: tuple[str, ...] = ()
    direct_backend_execution_allowed: bool = False

    def engine_for_model_policy(self, model_policy: str) -> str:
        return self.model_policy_map.get(model_policy, self.test_engine)


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("1", "true", "yes")
    return default


def load_execution_strategy(path: Path | None = None) -> ExecutionStrategy:
    strategy_path = path or Path(os.environ.get("EXECUTION_STRATEGY_PATH", DEFAULT_STRATEGY_PATH))
    raw = yaml.safe_load(strategy_path.read_text(encoding="utf-8")) or {}
    read_only = raw.get("read_only") or {}
    external = raw.get("external_agent_backends") or {}
    direct = raw.get("direct_backend_execution") or {}
    model_policy_map = dict(raw.get("model_policy_map") or {})
    if not model_policy_map:
        model_policy_map = {
            "fake": raw.get("test_engine", ENGINE_FAKE),
            "test": raw.get("test_engine", ENGINE_FAKE),
            "official": raw.get("default_engine", ENGINE_OFFICIAL),
            "balanced": raw.get("fallback_engine", ENGINE_MINIMAL),
            "local": raw.get("fallback_engine", ENGINE_MINIMAL),
            "readonly": raw.get("fallback_engine", ENGINE_MINIMAL),
        }
    return ExecutionStrategy(
        schema_version=str(raw.get("schema_version", "execution_strategy.v1")),
        default_engine=str(raw.get("default_engine", ENGINE_OFFICIAL)),
        fallback_engine=str(raw.get("fallback_engine", ENGINE_MINIMAL)),
        test_engine=str(raw.get("test_engine", ENGINE_FAKE)),
        model_policy_map=model_policy_map,
        read_only_max_prompt_chars=int(read_only.get("max_prompt_chars", 12000)),
        read_only_max_context_files=int(read_only.get("max_context_files", 5)),
        rlms_max_iterations_cap=int(read_only.get("rlms_max_iterations_cap", 3)),
        rlms_max_depth_cap=int(read_only.get("rlms_max_depth_cap", 0)),
        external_agent_backends_mode=str(external.get("mode", "rlm_tool_only")),
        external_agent_backends_allowed=tuple(external.get("allowed") or ()),
        direct_backend_execution_allowed=_coerce_bool(direct.get("allowed"), False),
    )


@lru_cache(maxsize=1)
def get_execution_strategy() -> ExecutionStrategy:
    return load_execution_strategy()
