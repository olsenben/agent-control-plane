"""V5 T05 — SARIF ingest → graph security/evidence nodes."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from agent_control.cli import main
from agent_control.graph.sarif_ingest import RISK_CLASS_CEILING, ingest_sarif
from agent_control.graph.store import GraphStore

FIXTURE = Path(__file__).parent / "fixtures" / "sample_t05.sarif.json"


def test_ingest_sample_sarif_attaches_evidence_nodes(tmp_path: Path, graph_settings) -> None:
    repo = "ai-sdlc-lab/agent-control-plane"
    store = GraphStore(graph_settings.graph_db_path)
    store.init_schema()

    report = ingest_sarif(repo, FIXTURE, settings=graph_settings, store=store)
    assert report["schema"] == "sarif_ingest_report.v1"
    assert report["ok"] is True
    assert report["findings_count"] == 2
    assert report["edges_attached"] >= 5  # 1 covers_repo + 2*2 finding edges
    assert report["risk_tags"] == ["security_finding"]
    assert report["risk_class_ceiling"] == RISK_CLASS_CEILING == 1
    assert report["blocks_risk2"] is False
    assert "src/agent_control/cli.py" in report["files_touched"]
    assert "src/agent_control/config.py" in report["files_touched"]

    edges = store.list_edges(repo)
    kinds = {e["kind"] for e in edges}
    assert "finding_affects_file" in kinds
    assert "tool_run_produced_finding" in kinds
    assert "tool_run_covers_repo" in kinds
    assert all(e.get("provenance") == "static_analysis" for e in edges)

    finding_edges = [e for e in edges if e["kind"] == "finding_affects_file"]
    assert len(finding_edges) == 2
    dsts = {e["dst"] for e in finding_edges}
    assert "file:src/agent_control/cli.py" in dsts
    assert "file:src/agent_control/config.py" in dsts

    with store.connect() as conn:
        paths = {r["path"] for r in conn.execute("SELECT path FROM files WHERE repo = ?", (repo,))}
    assert "src/agent_control/cli.py" in paths


def test_reingest_same_sarif_is_idempotent(graph_settings) -> None:
    repo = "ai-sdlc-lab/demo-sarif"
    store = GraphStore(graph_settings.graph_db_path)
    first = ingest_sarif(repo, FIXTURE, settings=graph_settings, store=store)
    second = ingest_sarif(repo, FIXTURE, settings=graph_settings, store=store)
    assert first["edges_attached"] == second["edges_attached"]
    edges = store.list_edges(repo, kind="finding_affects_file")
    assert len(edges) == 2


def test_missing_sarif_fail_soft(graph_settings, tmp_path: Path) -> None:
    report = ingest_sarif(
        "ai-sdlc-lab/demo",
        tmp_path / "missing.sarif",
        settings=graph_settings,
    )
    assert report["ok"] is False
    assert report["blocks_risk2"] is False
    assert report["risk_class_ceiling"] == 1


def test_graph_sarif_ingest_cli(graph_settings, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_STATE_ROOT", str(graph_settings.agent_state_root))
    monkeypatch.setenv("AGENT_CACHE_DIR", str(graph_settings.agent_cache_dir))
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "graph",
            "sarif-ingest",
            "--repo",
            "ai-sdlc-lab/agent-control-plane",
            "--file",
            str(FIXTURE),
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["ok"] is True
    assert data["findings_count"] == 2
    assert data["blocks_risk2"] is False
