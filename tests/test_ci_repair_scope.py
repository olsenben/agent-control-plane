"""Tests for CI repair approval scope resolution."""

from __future__ import annotations

from pathlib import Path

from agent_control.approval.storage import save_approval
from agent_control.ci.scope import resolve_allowed_files_for_fix
from agent_shared.models.approval import WorkItemApproval


def test_resolve_allowed_files_from_reserved_fix(tmp_path: Path) -> None:
    approval = WorkItemApproval(
        approval_id="appr-1",
        approval_target_id="WI-0004",
        plan_alias="PLAN-x",
        plan_run_id="run-plan",
        plan_hash="abc",
        blast_radius_hash="def",
        project="ai-sdlc-lab/demo-app",
        issue_id=4,
        allowed_files=["src/demo_app/math_service.py", "tests/test_math_service.py"],
        approved_by_login="olsenben",
        approved_at="2026-07-17T00:00:00+00:00",
        expires_at="2026-07-20T00:00:00+00:00",
        status="consumed",
        reserved_by_fix_run_id="run-fix-1",
        consumed_by_run_id="run-fix-1",
    )
    save_approval(tmp_path, approval)
    files = resolve_allowed_files_for_fix(
        tmp_path,
        repository="ai-sdlc-lab/demo-app",
        fix_run_id="run-fix-1",
        issue_id=4,
    )
    assert files == ["src/demo_app/math_service.py", "tests/test_math_service.py"]
