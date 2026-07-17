"""Plan quality gate — fixability before approval / fix workflow."""

from __future__ import annotations

from dataclasses import dataclass

from agent_shared.models.plan import PlanResult

REPLAN_HINT = (
    "Re-run planning with explicit target files, "
    "for example: /agent plan Update README.md to ..."
)
REPLAN_COMMAND = "/agent plan Update README.md to ..."


@dataclass(frozen=True)
class PlanQualityResult:
    fixable: bool
    reasons: list[str]


def evaluate_plan_quality(
    plan: PlanResult,
    *,
    path_validation_warnings: list[str] | None = None,
) -> PlanQualityResult:
    """Evaluate fixability after path validation on step.files."""
    from agent_workers.rlm.review_parser import PSEUDO_CONTEXT_SOURCES

    warnings = path_validation_warnings or []
    has_path_rejections = any(
        "Rejected hallucinated step file paths" in warning for warning in warnings
    )

    valid_step_files = [
        file
        for step in plan.steps
        for file in step.files
        if file.strip() and file.strip() not in PSEUDO_CONTEXT_SOURCES
    ]
    fixable = bool(plan.steps) and bool(valid_step_files)
    if fixable:
        return PlanQualityResult(fixable=True, reasons=[])

    reasons: list[str] = []
    if not plan.steps:
        reasons.append("Plan has no steps.")
    elif has_path_rejections and not valid_step_files:
        reasons.append("Plan referenced files, but none passed repository path validation.")
    else:
        reasons.append("Plan steps do not reference any valid repository files.")
    reasons.append(REPLAN_HINT)
    return PlanQualityResult(fixable=False, reasons=reasons)
