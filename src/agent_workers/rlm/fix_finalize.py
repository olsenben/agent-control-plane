"""Shared fix result finalization for RLM engines."""

from __future__ import annotations

from typing import Any

from agent_shared.constants import GITEA_COMMENT_SUMMARY_PROMPT_BUDGET_CHARS
from agent_shared.models.fix import FixFileChange, FixResult
from agent_shared.patch_paths import PatchPathError, validate_allowed_patch_path
from agent_workers.formatters.fix_comment import render_fix_comment
from agent_workers.rlm.budget import fit_summary_for_comment


def apply_path_validation(
    fix: FixResult,
    allowed_files: list[str],
) -> tuple[FixResult, list[str]]:
    warnings: list[str] = []
    validated_changes: list[FixFileChange] = []
    for change in fix.changes:
        try:
            normalized = validate_allowed_patch_path(change.path, allowed_files)
            validated_changes.append(change.model_copy(update={"path": normalized}))
        except PatchPathError as exc:
            warnings.append(str(exc))
    files_changed = sorted({c.path for c in validated_changes})
    return fix.model_copy(
        update={"changes": validated_changes, "files_changed": files_changed}
    ), warnings


def finalize_fix_result(
    fix: FixResult,
    *,
    job: dict[str, Any],
    engine: str,
) -> tuple[str, FixResult, list[str]]:
    del engine
    binding = job.get("fix_authorization") or {}
    allowed_files = list(binding.get("allowed_files") or [])
    validated, warnings = apply_path_validation(fix, allowed_files)
    validated = validated.model_copy(
        update={
            "approval_target_id": binding.get("approval_target_id") or validated.approval_target_id,
            "plan_run_id": binding.get("plan_run_id") or validated.plan_run_id,
            "ci_hints": list(binding.get("ci_hints") or validated.ci_hints),
        }
    )
    summary = fit_summary_for_comment(
        render_fix_comment(validated, patch_artifact="patch.diff"),
        GITEA_COMMENT_SUMMARY_PROMPT_BUDGET_CHARS,
    )
    return summary, validated, warnings
