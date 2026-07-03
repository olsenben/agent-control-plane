"""Shared plan result finalization for RLM engines."""

from __future__ import annotations

from typing import Any

from agent_shared.approval_ids import derive_approval_target_id, derive_plan_alias
from agent_shared.constants import GITEA_COMMENT_SUMMARY_PROMPT_BUDGET_CHARS
from agent_shared.models.plan import PlanResult, PriorMemoryUsed
from agent_shared.models.review import stub_blast_radius
from agent_workers.formatters.plan_comment import render_plan_comment
from agent_workers.rlm.budget import fit_summary_for_comment
from agent_workers.rlm.plan_parser import apply_path_validation
from agent_workers.rlm.plan_quality import REPLAN_COMMAND, evaluate_plan_quality


def finalize_plan_result(
    plan: PlanResult,
    *,
    known_sources: list[str],
    job: dict[str, Any],
    engine: str,
) -> tuple[str, PlanResult, list[str]]:
    del engine
    known = set(known_sources)

    pack = None
    pack_raw = job.get("context_pack")
    if pack_raw:
        from agent_shared.models.context_pack import ContextPack

        pack = (
            pack_raw
            if isinstance(pack_raw, ContextPack)
            else ContextPack.model_validate(pack_raw)
        )
    if pack is not None:
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
                set(plan.blast_radius.missing_graph_edges or pack_blast.missing_graph_edges)
            )
            plan = plan.model_copy(
                update={
                    "blast_radius": pack_blast.model_copy(
                        update={"missing_graph_edges": merged_missing}
                    )
                    if not any(
                        [
                            plan.blast_radius.affected_repos,
                            plan.blast_radius.affected_services,
                            plan.blast_radius.affected_tests,
                            plan.blast_radius.related_adrs,
                        ]
                    )
                    else plan.blast_radius
                }
            )

    if not any(
        [
            plan.blast_radius.affected_repos,
            plan.blast_radius.affected_services,
            plan.blast_radius.affected_tests,
            plan.blast_radius.related_adrs,
            plan.blast_radius.missing_graph_edges,
        ]
    ):
        plan = plan.model_copy(update={"blast_radius": stub_blast_radius()})

    validated, warnings = apply_path_validation(plan, known)

    quality = evaluate_plan_quality(validated, path_validation_warnings=warnings)
    validated = validated.model_copy(
        update={
            "fixable": quality.fixable,
            "quality_gate_reasons": quality.reasons,
        }
    )

    run_id = str(job.get("run_id") or "")
    trigger_context = job.get("trigger_context") or {}
    issue_number = trigger_context.get("issue_number")
    if quality.fixable and run_id and issue_number is not None:
        approval_target_id = derive_approval_target_id(
            issue_id=int(issue_number),
            plan_run_id=run_id,
        )
        plan_alias = derive_plan_alias(run_id)
        validated = validated.model_copy(
            update={
                "approval_target_id": approval_target_id,
                "plan_alias": plan_alias,
                "recommended_next_command": f"/agent fix {approval_target_id}",
            }
        )
    elif not quality.fixable:
        validated = validated.model_copy(
            update={
                "approval_target_id": None,
                "plan_alias": None,
                "recommended_next_command": REPLAN_COMMAND,
            }
        )

    if pack is not None and pack.prior_memory and not validated.prior_memory_used:
        validated = validated.model_copy(
            update={
                "prior_memory_used": [
                    PriorMemoryUsed(
                        run_id=str(entry.get("run_id") or entry.get("source_run_id") or ""),
                        record_id=entry.get("record_id"),
                        used_for="plan_context",
                    )
                    for entry in pack.prior_memory
                    if entry.get("run_id") or entry.get("source_run_id")
                ]
            }
        )

    summary = fit_summary_for_comment(
        render_plan_comment(validated),
        GITEA_COMMENT_SUMMARY_PROMPT_BUDGET_CHARS,
    )
    return summary, validated, warnings
