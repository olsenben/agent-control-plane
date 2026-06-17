"""Shared review result finalization for RLM engines."""

from __future__ import annotations

from typing import Any

from agent_shared.constants import GITEA_COMMENT_SUMMARY_PROMPT_BUDGET_CHARS
from agent_shared.models.review import ReviewResult, stub_blast_radius
from agent_workers.formatters.review_comment import render_review_comment
from agent_workers.rlm.budget import fit_summary_for_comment
from agent_workers.rlm.review_parser import apply_path_validation


def finalize_review_result(
    review: ReviewResult,
    *,
    known_sources: list[str],
    job: dict[str, Any],
    engine: str,
) -> tuple[str, ReviewResult, list[str]]:
    del job, engine
    known = set(known_sources)
    if not any(
        [
            review.blast_radius.affected_repos,
            review.blast_radius.affected_services,
            review.blast_radius.affected_tests,
            review.blast_radius.related_adrs,
            review.blast_radius.missing_graph_edges,
        ]
    ):
        review = review.model_copy(update={"blast_radius": stub_blast_radius()})

    validated, warnings = apply_path_validation(review, known)
    summary = fit_summary_for_comment(
        render_review_comment(validated),
        GITEA_COMMENT_SUMMARY_PROMPT_BUDGET_CHARS,
    )
    return summary, validated, warnings
