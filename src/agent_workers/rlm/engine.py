"""RLM engine protocol, registry, and factory."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from agent_shared.models.runs import RLMResult
from agent_workers.config.execution_strategy import ExecutionStrategy, get_execution_strategy
from agent_workers.rlm.constants import ENGINE_FAKE, ENGINE_MINIMAL, ENGINE_OFFICIAL


@runtime_checkable
class RLMEngine(Protocol):
    name: str

    def run(
        self,
        job: dict[str, Any],
        workspace: Path,
        policy: dict[str, Any],
        *,
        artifact_dir: str | None = None,
        context_broker: Any | None = None,
        tools: Any | None = None,
    ) -> RLMResult: ...


MODEL_POLICY_TO_ENGINE: dict[str, str] = {
    "fake": ENGINE_FAKE,
    "test": ENGINE_FAKE,
    "balanced": ENGINE_MINIMAL,
    "local": ENGINE_MINIMAL,
    "readonly": ENGINE_MINIMAL,
    "official": ENGINE_OFFICIAL,
}


def resolve_engine_name(model_policy: str, strategy: ExecutionStrategy | None = None) -> str:
    strategy = strategy or get_execution_strategy()
    return strategy.engine_for_model_policy(model_policy)


def get_engine(model_policy: str, strategy: ExecutionStrategy | None = None) -> RLMEngine:
    engine_name = resolve_engine_name(model_policy, strategy)
    if engine_name == ENGINE_FAKE:
        from agent_workers.rlm.fake_engine import FakeRLMEngine

        return FakeRLMEngine()
    if engine_name == ENGINE_MINIMAL:
        from agent_workers.rlm.minimal_engine import MinimalLocalRLMEngine

        return MinimalLocalRLMEngine()
    if engine_name == ENGINE_OFFICIAL:
        from agent_workers.rlm.official_engine import OfficialRLMEngine

        return OfficialRLMEngine()
    from agent_workers.rlm.fake_engine import FakeRLMEngine

    return FakeRLMEngine()
