"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_control.config import Settings
from agent_control.graph.snapshot import snapshot_project


@pytest.fixture
def control_plane_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def graph_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    state = tmp_path / "agent-state"
    cache = tmp_path / "cache"
    state.mkdir()
    cache.mkdir()
    monkeypatch.setenv("AGENT_STATE_ROOT", str(state))
    monkeypatch.setenv("AGENT_CACHE_DIR", str(cache))
    return Settings()


@pytest.fixture
def indexed_graph(graph_settings: Settings, control_plane_root: Path):
    project = "ai-sdlc-lab/agent-control-plane"
    result = snapshot_project(
        project,
        settings=graph_settings,
        local_path=control_plane_root,
    )
    return graph_settings, result
