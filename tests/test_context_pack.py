"""Tests for context pack compiler."""

from agent_control.graph.context_pack import compile_context_pack, render_context_pack_text
from agent_shared.models.jobs import TriggerContext


def test_compile_context_pack_with_blast(indexed_graph) -> None:
    settings, _snapshot = indexed_graph
    trigger = TriggerContext(event_type="test", issue_number=29)
    pack = compile_context_pack(
        "ai-sdlc-lab/agent-control-plane",
        trigger,
        settings=settings,
        changed_files=["src/agent_control/workflows/dispatch.py"],
        issue_override={"title": "Review dispatch", "body": "Please review dispatch.py"},
    )
    assert pack.schema_version == "context_pack.v1"
    assert "graph_blast_radius" in pack.context_sources
    assert pack.blast_radius.affected_services
    assert "ct103-control-plane" in pack.blast_radius.affected_services
    text = render_context_pack_text(pack)
    assert "blast_radius" in text
    assert pack.issue_text is not None


def test_compile_context_pack_issue_only_missing_diff(graph_settings) -> None:
    trigger = TriggerContext(event_type="test", issue_number=29)
    pack = compile_context_pack(
        "ai-sdlc-lab/agent-control-plane",
        trigger,
        settings=graph_settings,
        issue_override={"title": "Review", "body": "Please review"},
    )
    assert "no diff available for issue-only review" in pack.blast_radius.missing_graph_edges


def test_context_pack_budget_truncation(graph_settings) -> None:
    trigger = TriggerContext(event_type="test", issue_number=1)
    long_body = "x" * 10000
    pack = compile_context_pack(
        "ai-sdlc-lab/agent-control-plane",
        trigger,
        settings=graph_settings,
        issue_override={"title": "T", "body": long_body},
    )
    assert pack.issue_text is not None
    assert len(pack.issue_text) <= 4000
