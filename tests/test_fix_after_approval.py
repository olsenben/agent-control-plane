"""Approve then fix authorizes; enqueue consumes approval (Slice 6B)."""

from pathlib import Path
from unittest.mock import patch

from agent_control.approval.handlers import handle_approval_commands
from agent_control.approval.service import authorize_fix, evaluate_fix_request, grant_approval
from agent_control.approval.storage import load_approval
from agent_control.events import load_project_events
from agent_shared.models.intent import CommandIntent
from conftest import seed_plan_completed


def test_fix_authorize_does_not_consume(tmp_path: Path) -> None:
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

    approval = load_approval(tmp_path, "ai-sdlc-lab/agent-control-plane", target)
    assert approval is not None
    assert approval.status == "approved"


@patch("agent_control.approval.handlers.enqueue_fix_after_authorization")
def test_fix_handler_enqueues_and_consumes(mock_enqueue, tmp_path: Path) -> None:
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
    mock_enqueue.return_value = {
        "enqueued": True,
        "run_id": "run-fix123",
        "job_id": "rlm-root-fix123",
    }
    trigger = {
        "event_id": "fix-ev",
        "payload": {
            "comment": {"body": f"/agent fix {target}", "id": 5003},
            "issue": {"number": 4},
        },
    }
    intent = CommandIntent(
        activated=True,
        activation="/agent",
        kind="fix",
        approval_target=target,
        natural_language_task=target,
        confidence=1.0,
    )
    result = handle_approval_commands(
        tmp_path,
        "ai-sdlc-lab/agent-control-plane",
        trigger,
        intent,
    )
    assert result["handled"] is True
    assert result["enqueue"]["enqueued"] is True
    mock_enqueue.assert_called_once()


def test_second_fix_blocked_after_consume(tmp_path: Path) -> None:
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
    authorize_fix(tmp_path, evaluation=ev, comment_id=5002)

    from agent_control.approval.service import consume_approval_for_fix

    approval = load_approval(tmp_path, "ai-sdlc-lab/agent-control-plane", target)
    assert approval is not None
    consume_approval_for_fix(
        tmp_path,
        approval,
        fix_run_id="run-consumed",
        consumed_event_id="evt-1",
    )

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
