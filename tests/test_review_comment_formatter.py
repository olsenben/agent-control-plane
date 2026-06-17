"""Tests for review comment formatter."""

from agent_shared.models.review import (
    BlastRadiusContext,
    ReviewFinding,
    ReviewResult,
    stub_blast_radius,
)
from agent_workers.formatters.review_comment import render_review_comment


def test_render_review_comment_all_sections() -> None:
    review = ReviewResult(
        findings=[
            ReviewFinding(
                id="F-001",
                severity="warn",
                summary="Potential issue in auth module",
                file="src/auth.py",
                confidence=0.7,
            )
        ],
        files_inspected=["src/auth.py", "README.md"],
        blast_radius=stub_blast_radius(),
        confidence="medium",
        recommended_next_command="/agent plan",
        risk_tags=["auth_bypass_risk"],
    )
    body = render_review_comment(review)
    assert "## Agent Review" in body
    assert "### Finding" in body
    assert "[F-001] (warn)" in body
    assert "### Files inspected" in body
    assert "- src/auth.py" in body
    assert "### Cross-repo / blast-radius context" in body
    assert "missing_graph_edges: not implemented" in body
    assert "### Confidence" in body
    assert "medium" in body
    assert "### Recommended next command" in body
    assert "/agent plan" in body
    assert "Risk tags: auth_bypass_risk" in body


def test_render_review_comment_empty_lists() -> None:
    review = ReviewResult(
        blast_radius=BlastRadiusContext(),
        confidence="low",
    )
    body = render_review_comment(review)
    assert "- (none)" in body
    assert "Potentially affected repos: (none)" in body
