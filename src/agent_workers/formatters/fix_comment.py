"""Render structured fix output as a Gitea issue comment."""

from __future__ import annotations

from agent_shared.models.diff_gate import CiMatrixSelection, DiffGateResult
from agent_shared.models.fix import FixResult
from agent_shared.models.publish import RemotePublishResult


def render_fix_comment(
    fix: FixResult,
    *,
    patch_artifact: str | None = None,
    ci_matrix: CiMatrixSelection | None = None,
) -> str:
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

    lines.extend(["", "### CI matrix (planned)"])
    if ci_matrix and (ci_matrix.narrow_tests or ci_matrix.workflows or ci_matrix.raw_hints):
        if ci_matrix.narrow_tests:
            lines.append("Narrow tests:")
            for item in ci_matrix.narrow_tests:
                lines.append(f"- `{item}`")
        if ci_matrix.workflows:
            lines.append("Workflows:")
            for item in ci_matrix.workflows:
                lines.append(f"- `{item}`")
        if ci_matrix.raw_hints:
            lines.append("Raw hints:")
            for hint in ci_matrix.raw_hints:
                lines.append(f"- {hint}")
        lines.append(f"- dispatch: `{ci_matrix.dispatch}`")
    elif fix.ci_hints:
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
            "Local patch passed closed-world diff gate — push/CI pending (6D/6E).",
            f"Confidence: {fix.confidence}",
        ]
    )
    return "\n".join(lines)


def render_fix_published_comment(
    fix: FixResult,
    *,
    publish: RemotePublishResult,
    ci_matrix: CiMatrixSelection | None = None,
) -> str:
    lines: list[str] = ["## Agent Fix (published)", ""]
    lines.extend(["### Scope", fix.scope_summary or "(none)", ""])
    lines.extend(["### Files changed"])
    for path in fix.files_changed or []:
        lines.append(f"- `{path}`")
    lines.extend(
        [
            "",
            "### Remote publish",
            f"- Branch: `{publish.agent_branch}`",
            f"- Head SHA: `{publish.head_commit_sha or 'unknown'}`",
        ]
    )
    if publish.opened_pr_number:
        lines.append(f"- PR: #{publish.opened_pr_number}")
    if publish.opened_pr_url:
        lines.append(f"- PR URL: {publish.opened_pr_url}")
    lines.extend(
        [
            "",
            "### Verification",
            "**Not verified.** CT102 CI truth pending (6E).",
            "Patch published to agent branch — not verified until CT102 CI passes.",
            f"Confidence: {fix.confidence}",
        ]
    )
    return "\n".join(lines)


def render_fix_publish_failed(
    *,
    run_id: str,
    stage: str,
    message: str,
    partial: RemotePublishResult | None = None,
) -> str:
    parts = [
        "## Fix publish failed (Risk 2)",
        "",
        f"Run: `{run_id}`",
        f"Stage: `{stage}`",
        f"Reason: {message}",
    ]
    if partial and partial.head_commit_sha:
        parts.extend(
            [
                "",
                "### Partial remote state",
                f"- Branch: `{partial.agent_branch}`",
                f"- Head SHA: `{partial.head_commit_sha}`",
                "- Reservation held — use resume-pr or operator cleanup.",
            ]
        )
    return "\n".join(parts)


def render_fix_quality_failed(
    *,
    run_id: str,
    reasons: list[str],
    fallback_attempted: bool,
) -> str:
    lines = [
        "## Fix failed quality gate (Risk 2)",
        "",
        "Model returned valid JSON but no usable file changes.",
        f"Run: `{run_id}`",
        "",
    ]
    for reason in reasons[:6]:
        lines.append(f"- {reason}")
    if fallback_attempted:
        lines.append("")
        lines.append("Retried once on GPU, then attempted external fixer fallback.")
    else:
        lines.append("")
        lines.append("Retried once on GPU. External fixer fallback was not configured.")
    lines.extend(["", "No patch was applied. Approval may be retried after replan."])
    return "\n".join(lines)


def render_fix_failed(
    *,
    run_id: str,
    stage: str,
    message: str,
    allowed_files_count: int,
    violation_codes: list[str] | None = None,
) -> str:
    parts = [
        "## Fix failed (Risk 2)",
        "",
        f"Run: `{run_id}`",
        f"Stage: `{stage}`",
        f"Reason: {message}",
        f"Allowed files: {allowed_files_count}",
    ]
    if violation_codes:
        parts.extend(["", "### Violation codes"])
        for code in violation_codes:
            parts.append(f"- `{code}`")
    parts.extend(
        [
            "",
            "No approved patch was promoted. See `raw_patch.diff` in run artifacts for inspection.",
            "Approval may need re-grant after infra recovery.",
        ]
    )
    return "\n".join(parts)


def render_fix_gate_failed(
    *,
    run_id: str,
    gate_result: DiffGateResult,
    allowed_files_count: int,
) -> str:
    codes = gate_result.violation_codes()
    summary = f"Closed-world diff gate failed ({len(codes)} violation(s))."
    return render_fix_failed(
        run_id=run_id,
        stage="diff_gate",
        message=summary,
        allowed_files_count=allowed_files_count,
        violation_codes=codes,
    )
