"""Tests for platform execution_strategy loading."""

from pathlib import Path

from agent_workers.config.execution_strategy import load_execution_strategy
from agent_workers.rlm.constants import ENGINE_FAKE, ENGINE_MINIMAL, ENGINE_OFFICIAL
from agent_workers.rlm.engine import resolve_engine_name


def test_default_execution_strategy_maps_policies() -> None:
    strategy = load_execution_strategy()
    assert strategy.test_engine == ENGINE_FAKE
    assert strategy.default_engine == ENGINE_OFFICIAL
    assert strategy.fallback_engine == ENGINE_MINIMAL
    assert resolve_engine_name("fake", strategy) == ENGINE_FAKE
    assert resolve_engine_name("official", strategy) == ENGINE_OFFICIAL
    assert resolve_engine_name("local", strategy) == ENGINE_MINIMAL


def test_execution_strategy_custom_file(tmp_path: Path) -> None:
    path = tmp_path / "execution_strategy.yml"
    path.write_text(
        """
schema_version: execution_strategy.v1
default_engine: minimal_local_rlm
fallback_engine: minimal_local_rlm
test_engine: fake_rlm
model_policy_map:
  fake: fake_rlm
  official: minimal_local_rlm
""",
        encoding="utf-8",
    )
    strategy = load_execution_strategy(path)
    assert resolve_engine_name("official", strategy) == ENGINE_MINIMAL
