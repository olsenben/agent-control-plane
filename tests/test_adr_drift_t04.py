"""V5 T04 — Architecture drift detector (ADR facts vs graph edges)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from agent_control.cli import main
from agent_control.graph.adr_drift import detect_adr_drift, edge_fingerprint
from agent_control.graph.store import GraphStore


def test_detect_missing_and_extra_edges(tmp_path: Path, graph_settings) -> None:
    repo = "ai-sdlc-lab/demo-drift"
    facts = [
        {
            "adr_id": "ADR-0099",
            "scope_globs": ["src/demo/a.py"],
            "scope_symbols": ["DemoSymbol"],
        }
    ]
    # Graph has file edge for a.py but wrong symbol + an undeclared extra file.
    graph_edges = [
        {
            "kind": "adr_constrains_file",
            "src_kind": "adr",
            "src": "adr:ADR-0099",
            "dst_kind": "file",
            "dst": "file:src/demo/a.py",
        },
        {
            "kind": "adr_constrains_file",
            "src_kind": "adr",
            "src": "adr:ADR-0099",
            "dst_kind": "file",
            "dst": "file:src/demo/extra.py",
        },
        {
            "kind": "adr_constrains_symbol",
            "src_kind": "adr",
            "src": "adr:ADR-0099",
            "dst_kind": "symbol",
            "dst": "symbol:WrongSymbol",
        },
        # Non-ADR kind must be ignored for drift compare.
        {
            "kind": "file_imports_file",
            "src_kind": "file",
            "src": "file:a.py",
            "dst_kind": "file",
            "dst": "file:b.py",
        },
    ]

    report = detect_adr_drift(
        repo,
        settings=graph_settings,
        adr_facts=facts,
        graph_edges=graph_edges,
    )
    assert report["schema"] == "adr_drift_report.v1"
    assert report["fail_soft"] is True
    assert report["ok"] is True
    assert report["drift"] is True
    assert report["risk_tags"] == ["architecture_drift"]

    missing = {(e["kind"], e["dst"]) for e in report["missing_edges"]}
    extra = {(e["kind"], e["dst"]) for e in report["extra_edges"]}
    assert ("adr_constrains_symbol", "symbol:DemoSymbol") in missing
    assert ("adr_constrains_file", "file:src/demo/extra.py") in extra
    assert ("adr_constrains_symbol", "symbol:WrongSymbol") in extra
    assert ("adr_constrains_file", "file:src/demo/a.py") not in missing
    assert ("adr_constrains_file", "file:src/demo/a.py") not in extra


def test_no_drift_when_aligned() -> None:
    facts = [
        {
            "adr_id": "ADR-0001",
            "scope_globs": ["src/x.py"],
            "scope_symbols": ["X"],
        }
    ]
    edges = [
        {
            "kind": "adr_constrains_file",
            "src_kind": "adr",
            "src": "adr:ADR-0001",
            "dst_kind": "file",
            "dst": "file:src/x.py",
        },
        {
            "kind": "adr_constrains_symbol",
            "src_kind": "adr",
            "src": "adr:ADR-0001",
            "dst_kind": "symbol",
            "dst": "symbol:X",
        },
    ]
    report = detect_adr_drift(
        "owner/repo",
        adr_facts=facts,
        graph_edges=edges,
    )
    assert report["drift"] is False
    assert report["missing_edges"] == []
    assert report["extra_edges"] == []
    assert report["risk_tags"] == []


def test_fail_soft_missing_graph_and_adr(tmp_path: Path, graph_settings) -> None:
    report = detect_adr_drift(
        "owner/missing",
        adr_dir=tmp_path / "no-such-adr",
        settings=graph_settings,
    )
    assert report["ok"] is True
    assert report["fail_soft"] is True
    assert "adr directory not found" in " ".join(report["warnings"])
    assert "graph snapshot not found" in " ".join(report["warnings"])
    assert isinstance(report["missing_edges"], list)
    assert isinstance(report["extra_edges"], list)


def test_fail_soft_store_read(tmp_path: Path, graph_settings) -> None:
    store = GraphStore(tmp_path / "graph.sqlite")
    store.init_schema()
    store.upsert_snapshot(
        "ai-sdlc-lab/agent-control-plane",
        files=["src/a.py"],
        services=[],
        tests=[],
        adrs=[{"adr_id": "ADR-0099", "title": "t", "source_path": ""}],
        edges=[
            {
                "kind": "adr_constrains_file",
                "src_kind": "adr",
                "src": "adr:ADR-0099",
                "dst_kind": "file",
                "dst": "file:src/a.py",
                "confidence": "high",
                "provenance": "catalog",
            }
        ],
    )
    facts = [
        {
            "adr_id": "ADR-0099",
            "scope_globs": ["src/a.py", "src/missing.py"],
            "scope_symbols": [],
        }
    ]
    report = detect_adr_drift(
        "ai-sdlc-lab/agent-control-plane",
        settings=graph_settings,
        store=store,
        adr_facts=facts,
    )
    assert report["ok"] is True
    assert report["drift"] is True
    assert any(e["dst"] == "file:src/missing.py" for e in report["missing_edges"])
    assert report["extra_count"] == 0


def test_cli_graph_drift_fail_soft(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = tmp_path / "agent-state"
    state.mkdir()
    monkeypatch.setenv("AGENT_STATE_ROOT", str(state))
    monkeypatch.setenv("AGENT_CACHE_DIR", str(tmp_path / "cache"))

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["graph", "drift", "--repo", "owner/absent"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "missing_edges" in payload
    assert "extra_edges" in payload
    assert payload["fail_soft"] is True


def test_cli_graph_drift_strict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = tmp_path / "agent-state"
    state.mkdir()
    monkeypatch.setenv("AGENT_STATE_ROOT", str(state))
    monkeypatch.setenv("AGENT_CACHE_DIR", str(tmp_path / "cache"))

    adr = tmp_path / "docs" / "adr"
    adr.mkdir(parents=True)
    (adr / "0099-demo.md").write_text(
        "---\nid: ADR-0099\ntitle: Demo\nstatus: proposed\ndate: 2026-07-20\n"
        "owners: [platform]\nscope:\n  globs: [src/only_in_adr.py]\n"
        "  symbols: []\ndecision_type: architecture\nenforcement: soft\n"
        "risk_level: low\nsupersedes: []\nsuperseded_by: []\n"
        "review_after: 2026-08-20\nagent_visibility: [review]\n---\n\n# Demo\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    soft = runner.invoke(
        main,
        ["graph", "drift", "--repo", "owner/r", "--adr-dir", str(adr)],
        catch_exceptions=False,
    )
    assert soft.exit_code == 0
    payload = json.loads(soft.output)
    assert payload["drift"] is True
    assert payload["missing_count"] >= 1

    strict = runner.invoke(
        main,
        ["graph", "drift", "--repo", "owner/r", "--adr-dir", str(adr), "--strict"],
    )
    assert strict.exit_code != 0


def test_edge_fingerprint_stable() -> None:
    a = {"kind": "adr_constrains_file", "src": "adr:A", "dst": "file:x"}
    b = {"kind": "adr_constrains_file", "src": "adr:A", "dst": "file:x", "extra": 1}
    assert edge_fingerprint(a) == edge_fingerprint(b)
