"""Resolve approval scope for a fix run (CI repair continuity)."""

from __future__ import annotations

from pathlib import Path

from agent_control.approval.storage import list_approvals


def resolve_allowed_files_for_fix(
    state_root: Path,
    *,
    repository: str,
    fix_run_id: str,
    issue_id: int | None,
) -> list[str]:
    """Return allowed_files from the approval that reserved/consumed this fix run."""
    if issue_id is None:
        return []
    matches: list[list[str]] = []
    for approval in list_approvals(state_root, repository, issue_id=issue_id):
        if (
            approval.reserved_by_fix_run_id == fix_run_id
            or approval.consumed_by_run_id == fix_run_id
        ):
            if approval.allowed_files:
                return list(approval.allowed_files)
        if approval.allowed_files and approval.status in (
            "approved",
            "reserved",
            "consumed",
        ):
            matches.append(list(approval.allowed_files))
    return matches[-1] if matches else []
