"""Commit message and PR body formatters for Slice 6D."""

from __future__ import annotations

from agent_shared.models.approval import FixAuthorizationBinding
from agent_shared.models.fix import FixResult


def build_commit_message(
    *,
    run_id: str,
    binding: FixAuthorizationBinding,
    approved_base_sha: str | None,
    invoked_by: str | None = None,
    session_id: str | None = None,
    approved_by: str | None = None,
) -> str:
    subject = f"agent(fix): {binding.approval_target_id} ({run_id})"
    trailers = [
        f"Agent-Run: {run_id}",
        f"Agent-Run-ID: {run_id}",
        f"Approval-ID: {binding.approval_id}",
        f"Approval-Target: {binding.approval_target_id}",
        f"Plan-Run-ID: {binding.plan_run_id}",
        f"Plan-Hash: {binding.plan_hash}",
        f"Blast-Radius-Hash: {binding.blast_radius_hash}",
        "Diff-Gate-Result: passed",
    ]
    if session_id:
        trailers.append(f"Agent-Session: {session_id}")
    if invoked_by:
        trailers.append(f"Invoked-By: {invoked_by}")
    if approved_by:
        trailers.append(f"Approved-By: {approved_by}")
    if approved_base_sha:
        trailers.append(f"Approved-Base-SHA: {approved_base_sha}")
    return subject + "\n\n" + "\n".join(trailers)


def build_pr_body(
    *,
    run_id: str,
    issue_number: int | None,
    binding: FixAuthorizationBinding,
    fix_result: FixResult,
    approved_base_sha: str | None,
    ci_hints: list[str] | None = None,
) -> str:
    lines = [
        "## Agent fix proposal",
        "",
        "Status: PR opened, CI verification pending",
    ]
    if issue_number is not None:
        lines.append(f"Issue: #{issue_number}")
    lines.extend(
        [
            f"Run: {run_id}",
            f"Approval: {binding.approval_id}",
            f"Plan: {binding.plan_run_id}",
            f"Blast radius hash: {binding.blast_radius_hash}",
            "Diff gate: passed",
        ]
    )
    if approved_base_sha:
        lines.append(f"Approved base SHA: {approved_base_sha}")
    lines.extend(["", "## Files changed"])
    if fix_result.files_changed:
        for path in fix_result.files_changed:
            lines.append(f"- {path}")
    else:
        lines.append("- (none)")
    lines.extend(["", "## CI matrix planned"])
    hints = ci_hints or fix_result.ci_hints or []
    if hints:
        for hint in hints:
            lines.append(f"- {hint}")
    else:
        lines.append("- (none)")
    lines.extend(
        [
            "",
            "## Safety notes",
            "- Branch-only write",
            "- No direct push to main",
            "- CT102 verification pending",
            "- **Not verified.** CT102 CI truth pending (6E).",
        ]
    )
    return "\n".join(lines)
