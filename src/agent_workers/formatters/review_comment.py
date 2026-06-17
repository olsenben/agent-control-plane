"""Render structured review output as a Gitea issue comment."""

from __future__ import annotations

from agent_shared.models.review import ReviewResult


def _format_list(items: list[str]) -> str:
    if not items:
        return "(none)"
    return ", ".join(items)


def render_review_comment(review: ReviewResult) -> str:
    lines: list[str] = ["## Agent Review", "", "### Finding"]
    if review.findings:
        for finding in review.findings:
            file_part = f" ({finding.file})" if finding.file else ""
            lines.append(f"- [{finding.id}] ({finding.severity}){file_part} {finding.summary}")
    else:
        lines.append("- (none)")

    if review.risk_tags:
        lines.extend(["", f"Risk tags: {', '.join(review.risk_tags)}"])

    lines.extend(["", "### Files inspected"])
    if review.files_inspected:
        for path in review.files_inspected:
            lines.append(f"- {path}")
    else:
        lines.append("- (none)")

    br = review.blast_radius
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

    lines.extend(
        [
            "",
            "### Confidence",
            review.confidence,
            "",
            "### Recommended next command",
            review.recommended_next_command,
        ]
    )
    return "\n".join(lines)
