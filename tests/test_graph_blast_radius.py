"""Tests for blast-radius computation."""

from agent_control.graph.blast_radius import compute_blast_radius


def test_blast_radius_dispatch_file(indexed_graph) -> None:
    settings, _snapshot = indexed_graph
    br = compute_blast_radius(
        "ai-sdlc-lab/agent-control-plane",
        ["src/agent_control/workflows/dispatch.py"],
        settings=settings,
    )
    assert "ct103-control-plane" in br.affected_services
    assert "ai-sdlc-lab/agent-control-plane" in br.affected_repos
    assert "tests/test_dispatch.py" in br.affected_tests
    assert "ADR-003-agent-state" in br.related_adrs or "ADR-007-command-risk-classes" in br.related_adrs


def test_blast_radius_missing_snapshot(graph_settings) -> None:
    br = compute_blast_radius(
        "ai-sdlc-lab/unknown",
        ["src/foo.py"],
        settings=graph_settings,
    )
    assert any("snapshot" in m for m in br.missing_graph_edges)
