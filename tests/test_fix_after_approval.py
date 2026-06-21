"""Approve then fix authorizes once."""

from pathlib import Path

from agent_control.approval.service import authorize_fix, evaluate_fix_request, grant_approval
from agent_control.events import load_project_events
from conftest import seed_plan_completed


def test_fix_after_approval(tmp_path: Path) -> None:
    target = seed_plan_completed(tmp_path)
    grant_approval(
        tmp_path,
        project="ai-sdlc-lab/agent-control-plane",
        issue_id=4,
        target=target,
        approver_login="ai-sdlc-lab",
        author_is_owner=True,
        comment_id=5001,
    )
    ev = evaluate_fix_request(
        tmp_path,
        project="ai-sdlc-lab/agent-control-plane",
        issue_id=4,
        target=target,
    )
    assert ev.policy_decision == "approved"
    body, _, created = authorize_fix(tmp_path, evaluation=ev, comment_id=5002)
    assert created and body is not None
    assert body.worker_enqueued is False
    assert body.next_slice == "6B"

    ev2 = evaluate_fix_request(
        tmp_path,
        project="ai-sdlc-lab/agent-control-plane",
        issue_id=4,
        target=target,
    )
    assert ev2.policy_decision == "blocked"
    events = load_project_events(tmp_path, "ai-sdlc-lab/agent-control-plane")
    authorized = [e for e in events if e.get("type") == "agent.fix_authorized"]
    assert len(authorized) == 1
