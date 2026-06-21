"""Approval service grant/reject/evaluate/consume."""

from pathlib import Path

from agent_control.approval.service import (
    authorize_fix,
    evaluate_fix_request,
    grant_approval,
    reject_approval,
)
from agent_control.approval.storage import load_approval
from conftest import seed_plan_completed


def test_grant_and_evaluate(tmp_path: Path) -> None:
    target = seed_plan_completed(tmp_path)
    approval, _, _ = grant_approval(
        tmp_path,
        project="ai-sdlc-lab/agent-control-plane",
        issue_id=4,
        target=target,
        approver_login="ai-sdlc-lab",
        author_is_owner=True,
    )
    assert approval is not None
    ev = evaluate_fix_request(
        tmp_path,
        project="ai-sdlc-lab/agent-control-plane",
        issue_id=4,
        target=target,
    )
    assert ev.policy_decision == "approved"


def test_reject_does_not_activate_fix(tmp_path: Path) -> None:
    target = seed_plan_completed(tmp_path)
    reject_approval(
        tmp_path,
        project="ai-sdlc-lab/agent-control-plane",
        issue_id=4,
        target=target,
        rejector_login="ai-sdlc-lab",
        author_is_owner=True,
        reject_reason="no",
    )
    ev = evaluate_fix_request(
        tmp_path,
        project="ai-sdlc-lab/agent-control-plane",
        issue_id=4,
        target=target,
    )
    assert ev.policy_decision == "blocked"


def test_consume_on_authorize(tmp_path: Path) -> None:
    target = seed_plan_completed(tmp_path)
    grant_approval(
        tmp_path,
        project="ai-sdlc-lab/agent-control-plane",
        issue_id=4,
        target=target,
        approver_login="ai-sdlc-lab",
        author_is_owner=True,
    )
    ev = evaluate_fix_request(
        tmp_path,
        project="ai-sdlc-lab/agent-control-plane",
        issue_id=4,
        target=target,
    )
    _, _, created = authorize_fix(tmp_path, evaluation=ev, comment_id=3001)
    assert created is True
    stored = load_approval(tmp_path, "ai-sdlc-lab/agent-control-plane", target)
    assert stored is not None
    assert stored.status == "consumed"
