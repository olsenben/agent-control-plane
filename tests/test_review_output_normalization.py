"""Tests for review output normalization and platform pre-merge."""

import json

from agent_shared.models.context_pack import ContextPack
from agent_shared.models.review import BlastRadiusContext
from agent_workers.rlm.review_parser import parse_review_output


def _sample_pack() -> ContextPack:
    return ContextPack(
        project="ai-sdlc-lab/demo-app",
        blast_radius=BlastRadiusContext(
            affected_repos=["ai-sdlc-lab/agent-control-plane"],
            affected_services=["ct103-control-plane"],
            affected_tests=["tests/test_review_parser.py"],
            related_adrs=["ADR-003-agent-state"],
            missing_graph_edges=[],
        ),
        context_sources=["graph:blast_radius"],
    )


def test_review_prose_blast_radius_without_pack() -> None:
    payload = {
        "findings": [{"id": "F-001", "severity": "info", "summary": "ok"}],
        "blast_radius": "Focus on parser boundary hardening across repos.",
    }
    result = parse_review_output(json.dumps(payload))
    assert result.blast_radius.missing_graph_edges
    assert result.blast_radius.missing_graph_edges[0].startswith("model_narrative:")


def test_review_pack_blast_wins_over_model_prose() -> None:
    pack = _sample_pack()
    payload = {
        "findings": [{"id": "F-001", "severity": "info", "summary": "ok"}],
        "blast_radius": "Model prose should not survive when pack exists.",
    }
    result = parse_review_output(json.dumps(payload), context_pack=pack)
    assert result.blast_radius.affected_repos == pack.blast_radius.affected_repos
    assert result.blast_radius.affected_tests == pack.blast_radius.affected_tests


def test_review_findings_as_strings_coerced() -> None:
    payload = {
        "findings": ["Missing error handling", "Add tests for parser"],
        "files_inspected": ["src/main.py"],
    }
    result = parse_review_output(json.dumps(payload))
    assert len(result.findings) == 2
    assert result.findings[0].id == "F-001"
    assert result.findings[0].summary == "Missing error handling"
    assert result.findings[0].severity == "info"


def test_review_files_inspected_scalar_coerced() -> None:
    payload = {
        "findings": [{"id": "F-001", "severity": "info", "summary": "ok"}],
        "files_inspected": "README.md",
    }
    result = parse_review_output(json.dumps(payload))
    assert result.files_inspected == ["README.md"]


def test_review_confidence_float_coerced() -> None:
    payload = {
        "findings": [{"id": "F-001", "severity": "info", "summary": "ok"}],
        "confidence": 0.9,
    }
    result = parse_review_output(json.dumps(payload))
    assert result.confidence == "high"


def test_review_confidence_string_preserved() -> None:
    payload = {
        "findings": [{"id": "F-001", "severity": "info", "summary": "ok"}],
        "confidence": "low",
    }
    result = parse_review_output(json.dumps(payload))
    assert result.confidence == "low"
