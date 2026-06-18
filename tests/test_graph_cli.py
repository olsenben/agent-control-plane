"""CLI smoke tests for graph commands."""

import json
from pathlib import Path

from click.testing import CliRunner

from agent_control.cli import main


def test_graph_snapshot_cli(control_plane_root: Path, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("AGENT_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv(
        "GRAPH_SNAPSHOT_REPOS",
        "ai-sdlc-lab/agent-control-plane",
    )
    runner = CliRunner()
    from agent_control.graph import snapshot as snapshot_mod

    original = snapshot_mod.snapshot_project

    def _local_snapshot(project, settings=None, *, local_path=None, store=None):
        return original(
            project,
            settings=settings,
            local_path=control_plane_root,
            store=store,
        )

    monkeypatch.setattr(snapshot_mod, "snapshot_project", _local_snapshot)
    result = runner.invoke(main, ["graph", "snapshot"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["summary"]["repos"] >= 1


def test_graph_blast_radius_cli(indexed_graph, monkeypatch) -> None:
    settings, _ = indexed_graph
    monkeypatch.setenv("AGENT_STATE_ROOT", str(settings.agent_state_root))
    monkeypatch.setenv("AGENT_CACHE_DIR", str(settings.agent_cache_dir))
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "graph",
            "blast-radius",
            "--repo",
            "ai-sdlc-lab/agent-control-plane",
            "--files",
            "src/agent_control/workflows/dispatch.py",
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert "ct103-control-plane" in data["affected_services"]
