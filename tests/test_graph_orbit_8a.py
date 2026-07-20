"""T05 / 8a Orbit-style graph edges with provenance."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from agent_control.cli import main
from agent_control.graph.blast_radius import compute_blast_radius, export_blast_radius_json
from agent_control.graph.coverage import export_coverage_json, export_edges_json
from agent_control.graph.extractors.packages import extract_package_edges
from agent_control.graph.extractors.sdlc_evidence import (
    extract_adr_constrain_edges,
    extract_pipeline_edges,
    extract_test_covers_edges,
)
from agent_control.graph.provenance import EXTRACTOR_VERSION
from agent_control.graph.store import GraphStore


def test_catalog_emits_adr_constrains_service() -> None:
    from agent_control.graph.catalog import CatalogComponent, catalog_edges

    edges = catalog_edges(
        "ai-sdlc-lab/demo",
        CatalogComponent(name="demo-svc", adr_refs=["ADR-001"]),
    )
    kinds = {e["kind"] for e in edges}
    assert "adr_constrains_service" in kinds
    assert "adr_mentions_service" in kinds
    assert all(e.get("provenance") == "catalog" for e in edges)


def test_adr_constrain_and_test_covers_edges() -> None:
    facts = [
        {
            "adr_id": "ADR-0099",
            "scope_globs": ["src/agent_control/graph/store.py"],
            "scope_symbols": ["GraphStore"],
        }
    ]
    adr_edges = extract_adr_constrain_edges(
        "ai-sdlc-lab/agent-control-plane",
        facts,
        known_files={"src/agent_control/graph/store.py"},
    )
    assert any(e["kind"] == "adr_constrains_file" for e in adr_edges)
    assert any(e["kind"] == "adr_constrains_symbol" for e in adr_edges)
    assert all(e["provenance"] == "catalog" for e in adr_edges)

    covers = extract_test_covers_edges(
        "ai-sdlc-lab/agent-control-plane",
        files=["src/agent_control/graph/store.py"],
        tests=["tests/test_store.py"],
    )
    assert covers
    assert covers[0]["kind"] == "test_covers_file"
    assert covers[0]["provenance"] == "inferred"


def test_pipeline_and_package_edges(control_plane_root: Path) -> None:
    pipe = extract_pipeline_edges("ai-sdlc-lab/agent-control-plane", control_plane_root)
    assert any(e["kind"] == "pipeline_verifies_repo" for e in pipe)
    assert all(e["provenance"] == "static_analysis" for e in pipe)

    pkgs = extract_package_edges("ai-sdlc-lab/agent-control-plane", control_plane_root)
    assert any(e["kind"] == "package_depends_on_package" for e in pkgs)
    assert all(e["provenance"] == "static_analysis" for e in pkgs)


def test_snapshot_orbit_provenance(indexed_graph) -> None:
    settings, result = indexed_graph
    assert result["extractor_version"] == EXTRACTOR_VERSION
    assert "provenance_counts" in result
    assert result["provenance_counts"].get("catalog", 0) > 0
    assert result["provenance_counts"].get("static_analysis", 0) > 0

    kinds = result["edge_kinds"]
    assert kinds.get("file_imports_file", 0) > 0
    assert kinds.get("adr_constrains_file", 0) > 0 or kinds.get("adr_constrains_symbol", 0) > 0
    assert kinds.get("package_depends_on_package", 0) > 0
    assert kinds.get("pipeline_verifies_repo", 0) > 0

    store = GraphStore(settings.graph_db_path)
    edges = store.list_edges("ai-sdlc-lab/agent-control-plane")
    assert edges
    assert all("provenance" in e for e in edges)
    meta = store.repo_meta("ai-sdlc-lab/agent-control-plane")
    assert meta is not None
    assert meta.get("extractor_version") == EXTRACTOR_VERSION


def test_coverage_and_edges_export(indexed_graph) -> None:
    settings, _ = indexed_graph
    coverage = export_coverage_json("ai-sdlc-lab/agent-control-plane", settings=settings)
    assert coverage["extractor_version"] == EXTRACTOR_VERSION
    assert coverage["edge_kinds"]
    assert coverage["provenance_counts"]
    assert "orbit_edge_kinds_expected" in coverage

    edges_payload = export_edges_json(
        "ai-sdlc-lab/agent-control-plane",
        kind="package_depends_on_package",
        settings=settings,
    )
    assert edges_payload["count"] > 0
    assert all(e["kind"] == "package_depends_on_package" for e in edges_payload["edges"])
    assert all(e["provenance"] == "static_analysis" for e in edges_payload["edges"])


def test_blast_radius_still_fail_soft(graph_settings) -> None:
    br = compute_blast_radius(
        "ai-sdlc-lab/unknown",
        ["src/foo.py"],
        settings=graph_settings,
    )
    assert any("snapshot" in m for m in br.missing_graph_edges)
    assert br.affected_services == []

    payload = export_blast_radius_json(
        "ai-sdlc-lab/unknown",
        ["src/foo.py"],
        settings=graph_settings,
    )
    assert payload["fail_soft"] is True
    assert payload["missing_edges"]


def test_graph_edges_and_coverage_cli(indexed_graph, monkeypatch) -> None:
    settings, _ = indexed_graph
    monkeypatch.setenv("AGENT_STATE_ROOT", str(settings.agent_state_root))
    monkeypatch.setenv("AGENT_CACHE_DIR", str(settings.agent_cache_dir))
    runner = CliRunner()

    edges_result = runner.invoke(
        main,
        [
            "graph",
            "edges",
            "--repo",
            "ai-sdlc-lab/agent-control-plane",
            "--provenance",
            "catalog",
            "--limit",
            "20",
        ],
    )
    assert edges_result.exit_code == 0, edges_result.output
    edges_data = json.loads(edges_result.output)
    assert edges_data["count"] > 0
    assert edges_data["provenance_counts"].get("catalog", 0) > 0

    cov_result = runner.invoke(
        main,
        ["graph", "coverage", "--repo", "ai-sdlc-lab/agent-control-plane"],
    )
    assert cov_result.exit_code == 0, cov_result.output
    cov_data = json.loads(cov_result.output)
    assert "adr_constrains_service" in cov_data["edge_kinds"] or "adr_mentions_service" in cov_data[
        "edge_kinds"
    ]


def test_schema_migration_adds_provenance(tmp_path: Path) -> None:
    db = tmp_path / "legacy.db"
    import sqlite3

    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE repos (full_name TEXT PRIMARY KEY, snapshot_at TEXT NOT NULL);
        CREATE TABLE edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo TEXT NOT NULL,
            kind TEXT NOT NULL,
            src_kind TEXT NOT NULL,
            src TEXT NOT NULL,
            dst_kind TEXT NOT NULL,
            dst TEXT NOT NULL,
            confidence TEXT DEFAULT 'medium'
        );
        """
    )
    conn.close()

    store = GraphStore(db)
    store.init_schema()
    store.upsert_snapshot(
        "demo/repo",
        files=["a.py"],
        services=[],
        tests=[],
        adrs=[],
        edges=[
            {
                "kind": "repo_contains_file",
                "src_kind": "repo",
                "src": "repo:demo/repo",
                "dst_kind": "file",
                "dst": "file:a.py",
                "confidence": "high",
                "provenance": "static_analysis",
            }
        ],
        source_sha="abc",
    )
    edges = store.list_edges("demo/repo")
    assert edges[0]["provenance"] == "static_analysis"
    assert store.repo_meta("demo/repo")["source_sha"] == "abc"
