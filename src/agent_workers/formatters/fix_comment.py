"""Render structured fix output as a Gitea issue comment."""

from __future__ import annotations

from agent_shared.models.fix import FixResult


def render_fix_comment(fix: FixResult, *, patch_artifact: str | None = None) -> str:
    lines: list[str] = ["## Agent Fix (local patch)", ""]

    lines.extend(["### Scope", fix.scope_summary or "(none)", ""])

    lines.extend(["### Files changed"])
    if fix.files_changed:
        for path in fix.files_changed:
            lines.append(f"- `{path}`")
    else:
        lines.append("- (none)")

    if patch_artifact:
        lines.extend(["", "### Patch artifact", f"- `{patch_artifact}` (workspace-local only)"])

    lines.extend(["", "### CI hints (planned)"])
    if fix.ci_hints:
        for hint in fix.ci_hints:
            lines.append(f"- {hint}")
    else:
        lines.append("- (none)")

    if fix.risk_tags:
        lines.extend(["", f"Risk tags: {', '.join(fix.risk_tags)}"])

    lines.extend(
        [
            "",
            "### Verification",
            "Local patch only — push/CI pending (6D/6E).",
            f"Confidence: {fix.confidence}",
        ]
    )
    return "\n".join(lines)


def render_fix_failed(
    *,
    run_id: str,
    stage: str,
    message: str,
    allowed_files_count: int,
) -> str:
    return "\n".join(
        [
            "## Fix failed (Risk 2)",
            "",
            f"Run: `{run_id}`",
            f"Stage: `{stage}`",
            f"Reason: {message}",
            f"Allowed files: {allowed_files_count}",
            "",
            "No patch was applied. Approval may need re-grant after infra recovery.",
        ]
    )
