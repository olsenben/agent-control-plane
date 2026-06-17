"""Tests for review Pydantic models."""

from agent_shared.models.review import (
    BlastRadiusContext,
    ReviewFinding,
    ReviewResult,
    stub_blast_radius,
)


def test_stub_blast_radius() -> None:
    br = stub_blast_radius()
    assert br.missing_graph_edges == ["not implemented"]
    assert br.affected_repos == []


def test_review_result_defaults() -> None:
    result = ReviewResult()
    assert result.schema_version == "review_result.v1"
    assert result.recommended_next_command == "/agent plan"
    assert result.confidence == "medium"


def test_review_finding_validation() -> None:
    finding = ReviewFinding(id="F-001", summary="test", confidence=0.8)
    assert finding.severity == "info"
    assert finding.risk_tags == []
