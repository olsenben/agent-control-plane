"""Fix without approval is blocked."""

from pathlib import Path

from agent_control.approval.service import evaluate_fix_request, record_fix_request
from conftest import seed_plan_completed


def test_fix_blocked_without_approval(tmp_path: Path) -> None:
    target = seed_plan_completed(tmp_path)
    ev = evaluate_fix_request(
        tmp_path,
        project="ai-sdlc-lab/agent-control-plane",
        issue_id=4,
        target=target,
    )
    assert ev.policy_decision == "blocked"
    _, created = record_fix_request(
        tmp_path,
        project="ai-sdlc-lab/agent-control-plane",
        issue_id=4,
        target=target,
        requested_by_login="ai-sdlc-lab",
        comment_id=4001,
        evaluation=ev,
    )
    assert created is True
