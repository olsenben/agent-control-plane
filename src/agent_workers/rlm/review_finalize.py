"""Shared review result finalization for RLM engines."""

from __future__ import annotations

from pathlib import Path
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
    workspace: Path | str | None = None,
) -> tuple[str, ReviewResult, list[str]]:
    del engine
    known = set(known_sources)
    workspace_path = Path(workspace) if workspace else None

    pack = job.get("context_pack")
    if pack:
        from agent_shared.models.context_pack import ContextPack

        schema = (
            pack.get("schema_version")
            if isinstance(pack, dict)
            else getattr(pack, "schema_version", None)
        )
        if schema == "context-pack.v2":
            pack = None
        elif isinstance(pack, dict):
            pack = ContextPack.model_validate(pack)
    if pack:
        pack_blast = pack.blast_radius
        has_pack_data = any(
            [
                pack_blast.affected_repos,
                pack_blast.affected_services,
                pack_blast.affected_tests,
                pack_blast.related_adrs,
            ]
        )
        if has_pack_data:
            merged_missing = list(
                set(review.blast_radius.missing_graph_edges or pack_blast.missing_graph_edges)
            )
            review = review.model_copy(
                update={
                    "blast_radius": pack_blast.model_copy(
                        update={"missing_graph_edges": merged_missing}
                    )
                    if not any(
                        [
                            review.blast_radius.affected_repos,
                            review.blast_radius.affected_services,
                            review.blast_radius.affected_tests,
                            review.blast_radius.related_adrs,
                        ]
                    )
                    else review.blast_radius
                }
            )

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

    validated, warnings = apply_path_validation(
        review, known, workspace=workspace_path
    )
    summary = fit_summary_for_comment(
        render_review_comment(validated),
        GITEA_COMMENT_SUMMARY_PROMPT_BUDGET_CHARS,
    )
    return summary, validated, warnings
