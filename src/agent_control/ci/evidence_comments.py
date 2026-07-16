"""Failure-evidence comments and helpers (Slice 6F.1)."""

from __future__ import annotations

import logging

from agent_control.ci.log_sanitize import UNTRUSTED_CI_PREAMBLE
from agent_control.config import Settings, get_settings
from agent_control.gitea_comments import post_issue_comment
from agent_shared.models.ci import CiVerificationResult, FailureEvidenceManifest

logger = logging.getLogger(__name__)

EVIDENCE_MARKER_PREFIX = "<!-- agent-ci-failure-evidence:"


def evidence_comment_marker(observation_id: str) -> str:
    return f"{EVIDENCE_MARKER_PREFIX}{observation_id} -->"


def format_failure_evidence_comment(
    result: CiVerificationResult,
    manifest: FailureEvidenceManifest,
    *,
    excerpt: str = "",
) -> str:
    lines = [
        "## Fix CI failure evidence",
        "",
        f"Fix run: `{result.fix_run_id}`",
        f"Head SHA: `{result.expected_head_commit_sha}`",
        f"Workflow run: `{manifest.workflow_run_id}` "
        f"(attempt {manifest.workflow_run_attempt}"
        + (f", run_number={manifest.run_number}" if manifest.run_number is not None else "")
        + ")",
        f"Evidence status: **{manifest.status}**",
        f"Failure class: `{manifest.failure_class}`",
        "",
    ]
    if manifest.reason_codes:
        lines.append("Reasons: " + ", ".join(f"`{c}`" for c in manifest.reason_codes[:12]))
        lines.append("")
    if manifest.status == "collected" and excerpt:
        lines.append(UNTRUSTED_CI_PREAMBLE)
        lines.append("")
        # Keep comment excerpt small
        trimmed = excerpt[:1200]
        lines.append("```")
        lines.append(trimmed)
        lines.append("```")
        lines.append("")
    elif manifest.status != "collected":
        lines.append(
            "Evidence could not be collected. Automatic repair will not run. "
            "Operator attention may be required (`agent:blocked`)."
        )
        lines.append("")
    lines.append(evidence_comment_marker(manifest.evidence_observation_id))
    return "\n".join(lines)


def post_failure_evidence_comment(
    result: CiVerificationResult,
    manifest: FailureEvidenceManifest,
    *,
    excerpt: str = "",
    settings: Settings | None = None,
) -> dict | None:
    settings = settings or get_settings()
    issue = result.issue_id or result.opened_pr_number
    if issue is None:
        return None
    body = format_failure_evidence_comment(result, manifest, excerpt=excerpt)
    try:
        return post_issue_comment(result.repository, issue, body, settings=settings)
    except Exception:
        logger.exception(
            "ci_failure_evidence_comment_failed fix_run_id=%s obs=%s",
            result.fix_run_id,
            manifest.evidence_observation_id,
        )
        return None
