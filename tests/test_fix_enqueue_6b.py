"""Fix enqueue path tests (Slice 6B)."""

from pathlib import Path
from unittest.mock import patch

import pytest

from agent_control.approval.dispatch_fix import build_fix_rlm_job, enqueue_fix_after_authorization
from agent_control.approval.handlers import handle_approval_commands
from agent_control.approval.storage import load_approval
from agent_control.events import load_project_events
from agent_shared.models.intent import CommandIntent
from conftest import sample_plan, seed_plan_completed
from agent_control.approval.service import grant_approval


def test_build_fix_rlm_job_has_binding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_STATE_ROOT", str(tmp_path))
    target = seed_plan_completed(tmp_path)
    approval, _, _ = grant_approval(
        tmp_path,
        project="ai-sdlc-lab/agent-control-plane",
        issue_id=4,
        target=target,
        approver_login="owner",
        author_is_owner=True,
    )
    assert approval is not None
    from agent_control.approval.plan_lookup import resolve_plan_for_target

    record = resolve_plan_for_target(tmp_path, "ai-sdlc-lab/agent-control-plane", 4, target)
    trigger = {"event_id": "t1", "payload": {"comment": {"body": "/agent fix"}, "issue": {"number": 4}}}
    job = build_fix_rlm_job(
        trigger_event=trigger,
        evaluation_approval=approval,
        plan_record=record,
    )
    assert job.risk_class == "write_patch"
    assert job.safety.allow_push is False
    assert job.fix_authorization is not None
    assert job.fix_authorization.allowed_files


@patch("agent_control.approval.dispatch_fix.enqueue_rlm_root", return_value="job-1")
def test_enqueue_emits_fix_enqueued(mock_enqueue, tmp_path: Path) -> None:
    target = seed_plan_completed(tmp_path)
    approval, _, _ = grant_approval(
        tmp_path,
        project="ai-sdlc-lab/agent-control-plane",
        issue_id=4,
        target=target,
        approver_login="owner",
        author_is_owner=True,
    )
    assert approval is not None
    from agent_control.approval.plan_lookup import resolve_plan_for_target

    record = resolve_plan_for_target(tmp_path, "ai-sdlc-lab/agent-control-plane", 4, target)
    result = enqueue_fix_after_authorization(
        tmp_path,
        trigger_event={"event_id": "t2", "payload": {"comment": {"id": 1}, "issue": {"number": 4}}},
        approval=approval,
        plan_record=record,
        comment_id=99,
    )
    assert result["enqueued"] is True
    events = load_project_events(tmp_path, "ai-sdlc-lab/agent-control-plane")
    types = [e.get("type") for e in events]
    assert "agent.fix_enqueued" in types
    assert "agent.approval_consumed" in types
    stored = load_approval(tmp_path, "ai-sdlc-lab/agent-control-plane", target)
    assert stored is not None
    assert stored.status == "consumed"


@patch("agent_control.approval.dispatch_fix.enqueue_rlm_root", return_value=None)
def test_enqueue_failure_does_not_consume(mock_enqueue, tmp_path: Path) -> None:
    target = seed_plan_completed(tmp_path)
    approval, _, _ = grant_approval(
        tmp_path,
        project="ai-sdlc-lab/agent-control-plane",
        issue_id=4,
        target=target,
        approver_login="owner",
        author_is_owner=True,
    )
    assert approval is not None
    from agent_control.approval.plan_lookup import resolve_plan_for_target

    record = resolve_plan_for_target(tmp_path, "ai-sdlc-lab/agent-control-plane", 4, target)
    result = enqueue_fix_after_authorization(
        tmp_path,
        trigger_event={"event_id": "t3"},
        approval=approval,
        plan_record=record,
        comment_id=100,
    )
    assert result["enqueued"] is False
    stored = load_approval(tmp_path, "ai-sdlc-lab/agent-control-plane", target)
    assert stored is not None
    assert stored.status == "approved"


def test_empty_allowed_files_blocks_before_enqueue(tmp_path: Path) -> None:
    plan = sample_plan(with_files=False)
    target = seed_plan_completed(tmp_path, plan=plan)
    grant_approval(
        tmp_path,
        project="ai-sdlc-lab/agent-control-plane",
        issue_id=4,
        target=target,
        approver_login="owner",
        author_is_owner=True,
        comment_id=1,
    )
    trigger = {
        "event_id": "empty",
        "payload": {"comment": {"body": f"/agent fix {target}", "id": 2}, "issue": {"number": 4}},
    }
    intent = CommandIntent(
        activated=True,
        activation="/agent",
        kind="fix",
        approval_target=target,
        natural_language_task=target,
        confidence=1.0,
    )
    with patch("agent_control.approval.handlers.enqueue_fix_after_authorization") as mock_enqueue:
        result = handle_approval_commands(
            tmp_path,
            "ai-sdlc-lab/agent-control-plane",
            trigger,
            intent,
        )
        mock_enqueue.assert_not_called()
    assert result.get("reason") == "empty_allowed_files"
