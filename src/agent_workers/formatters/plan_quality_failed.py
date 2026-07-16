"""Plan quality gate failure comment (Slice 6D.1)."""


def render_plan_quality_failed(*, run_id: str, reasons: list[str], fallback_attempted: bool) -> str:
    lines = [
        "## Plan failed quality gate (Risk 1)",
        "",
        "Model returned valid JSON but no actionable steps.",
        f"Run: `{run_id}`",
        "",
    ]
    for reason in reasons[:6]:
        lines.append(f"- {reason}")
    if fallback_attempted:
        lines.extend(
            [
                "",
                "Retried once on GPU, then attempted external planner fallback.",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "Retried once on GPU. External planner fallback was not configured.",
            ]
        )
    lines.extend(["", "Re-run with `/agent plan Update README.md to ...`"])
    return "\n".join(lines)
