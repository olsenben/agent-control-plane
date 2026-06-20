"""Render structured plan output as a Gitea issue comment."""

from __future__ import annotations

from agent_shared.models.plan import PlanResult
from agent_workers.formatters.review_comment import _format_list


def render_plan_comment(plan: PlanResult) -> str:
    lines: list[str] = ["## Agent Plan", ""]

    lines.extend(["### Scope", plan.scope_summary or "(none)", ""])

    lines.extend(["### Steps"])
    if plan.steps:
        for step in plan.steps:
            files_part = f" ({', '.join(step.files)})" if step.files else ""
            lines.append(f"- [{step.id}]{files_part} {step.summary}")
    else:
        lines.append("- (none)")

    lines.extend(["", "### CI hints"])
    if plan.ci_hints:
        for hint in plan.ci_hints:
            lines.append(f"- {hint}")
    else:
        lines.append("- (none)")

    br = plan.blast_radius
    lines.extend(
        [
            "",
            "### Cross-repo / blast-radius context",
            f"Potentially affected repos: {_format_list(br.affected_repos)}",
            f"Potentially affected services: {_format_list(br.affected_services)}",
            f"Potentially affected tests: {_format_list(br.affected_tests)}",
            f"Related ADRs: {_format_list(br.related_adrs)}",
        ]
    )
    if br.missing_graph_edges:
        lines.append(f"missing_graph_edges: {', '.join(br.missing_graph_edges)}")
    else:
        lines.append("missing_graph_edges: (none)")

    if plan.assumptions:
        lines.extend(["", "### Assumptions"])
        for item in plan.assumptions:
            lines.append(f"- {item}")

    if plan.open_questions:
        lines.extend(["", "### Open questions"])
        for item in plan.open_questions:
            lines.append(f"- {item}")

    if plan.risk_tags:
        lines.extend(["", f"Risk tags: {', '.join(plan.risk_tags)}"])

    lines.extend(
        [
            "",
            "### Confidence",
            plan.confidence,
            "",
            "### Recommended next command",
            plan.recommended_next_command,
        ]
    )
    return "\n".join(lines)
