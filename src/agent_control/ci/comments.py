"""CI status Gitea comments with hidden markers (Slice 6E.1)."""

from __future__ import annotations

import logging

from agent_control.config import Settings, get_settings
from agent_control.gitea_comments import post_issue_comment
from agent_shared.models.ci import CiVerificationResult

logger = logging.getLogger(__name__)

MARKER_PREFIX = "<!-- agent-ci-status:"


def comment_marker(fix_run_id: str, verdict_revision: int) -> str:
    return f"{MARKER_PREFIX}{fix_run_id}:rev{verdict_revision} -->"


def format_ci_status_comment(result: CiVerificationResult) -> str:
    lines = [
        "## Fix CI status",
        "",
        f"Fix run: `{result.fix_run_id}`",
        f"Head SHA: `{result.expected_head_commit_sha}`",
        f"Verdict: **{result.verdict}** (rev {result.verdict_revision})",
        "",
    ]
    if result.required_workflows:
        lines.append("Required workflows:")
        for req in result.required_workflows:
            label = req.path or req.display_name or req.workflow_id or "(unnamed)"
            lines.append(f"- `{label}`")
        lines.append("")
    if result.missing_workflows:
        lines.append("Missing:")
        for item in result.missing_workflows:
            lines.append(f"- `{item}`")
        lines.append("")
    if result.reason_codes:
        lines.append("Reasons: " + ", ".join(f"`{c}`" for c in result.reason_codes[:12]))
        lines.append("")
    if result.verdict == "verified":
        lines.append("CT102 verified for this exact head commit. Memory writeback eligible (6E.2).")
    elif result.verdict == "failing":
        lines.append(
            "One or more required workflows failed. "
            "Failure evidence is collected when FIX_CI_FAILURE_EVIDENCE_ENABLED is on. "
            "Automatic repair stays gated (`FIX_CI_REPAIR_ENABLED`, sandbox attestation)."
        )
    elif result.verdict == "pending":
        lines.append("Awaiting required workflow terminal results for this SHA.")
    lines.append("")
    lines.append(comment_marker(result.fix_run_id, result.verdict_revision))
    return "\n".join(lines)


def post_ci_status_comment(
    result: CiVerificationResult,
    *,
    settings: Settings | None = None,
) -> dict | None:
    """Post status comment. Failure must not roll back ledger events (caller catches)."""
    settings = settings or get_settings()
    issue = result.issue_id or result.opened_pr_number
    if issue is None:
        logger.info("ci_comment_skip fix_run_id=%s no issue/pr", result.fix_run_id)
        return None
    body = format_ci_status_comment(result)
    try:
        return post_issue_comment(result.repository, issue, body, settings=settings)
    except Exception:
        logger.exception(
            "ci_comment_failed fix_run_id=%s issue=%s",
            result.fix_run_id,
            issue,
        )
        return None
