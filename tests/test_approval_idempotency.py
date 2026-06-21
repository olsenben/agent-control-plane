"""Idempotent approval ledger writes."""

from pathlib import Path

from agent_control.approval.service import grant_approval
from agent_control.events import load_project_events
from conftest import seed_plan_completed


def test_duplicate_approve_one_granted_event(tmp_path: Path) -> None:
    target = seed_plan_completed(tmp_path)
    project = "ai-sdlc-lab/agent-control-plane"
    grant_approval(
        tmp_path,
        project=project,
        issue_id=4,
        target=target,
        approver_login="ai-sdlc-lab",
        author_is_owner=True,
        comment_id=1001,
    )
    grant_approval(
        tmp_path,
        project=project,
        issue_id=4,
        target=target,
        approver_login="ai-sdlc-lab",
        author_is_owner=True,
        comment_id=1001,
    )
    events = load_project_events(tmp_path, project)
    granted = [e for e in events if e.get("type") == "human.approval_granted"]
    assert len(granted) == 1
