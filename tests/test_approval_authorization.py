"""Owner-only approve and reject."""

from pathlib import Path

from agent_control.approval.service import grant_approval, reject_approval
from agent_control.events import load_project_events
from conftest import seed_plan_completed


def test_non_owner_cannot_grant(tmp_path: Path) -> None:
    target = seed_plan_completed(tmp_path)
    approval, message, created = grant_approval(
        tmp_path,
        project="ai-sdlc-lab/agent-control-plane",
        issue_id=4,
        target=target,
        approver_login="random-user",
        author_is_owner=False,
        comment_id=2001,
    )
    assert approval is None
    assert created is False
    events = load_project_events(tmp_path, "ai-sdlc-lab/agent-control-plane")
    assert not any(e.get("type") == "human.approval_granted" for e in events)


def test_non_owner_reject_no_event(tmp_path: Path) -> None:
    target = seed_plan_completed(tmp_path)
    ok, _, created = reject_approval(
        tmp_path,
        project="ai-sdlc-lab/agent-control-plane",
        issue_id=4,
        target=target,
        rejector_login="random-user",
        author_is_owner=False,
    )
    assert ok is False
    assert created is False
