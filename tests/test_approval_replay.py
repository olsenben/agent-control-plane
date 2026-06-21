"""Ledger replay rebuilds approval state."""

from agent_control.events import AgentEvent, append_event
from agent_control.state_reducer import reduce_event_only
from agent_shared.models.approval import WorkItemApproval
from conftest import seed_plan_completed


def test_replay_approval_granted(tmp_path) -> None:
    target = seed_plan_completed(tmp_path)
    project = "ai-sdlc-lab/agent-control-plane"
    approval = WorkItemApproval(
        approval_id="appr-test",
        approval_target_id=target,
        plan_alias="PLAN-run-dc0b71eb",
        plan_run_id="run-dc0b71ebebb3379b440471e2caa2b9cc",
        plan_hash="abc",
        blast_radius_hash="def",
        project=project,
        issue_id=4,
        approved_by_login="ai-sdlc-lab",
        approved_at="2026-06-17T12:00:00+00:00",
        expires_at="2026-12-31T00:00:00+00:00",
    )
    append_event(
        tmp_path,
        AgentEvent(
            event_id="appr-evt-1",
            type="human.approval_granted",
            project=project,
            payload=approval.model_dump(mode="json"),
            recorded_at="2026-06-17T13:00:00+00:00",
        ),
    )
    from agent_control.events import load_project_events

    state = reduce_event_only(load_project_events(tmp_path, project), project)
    assert target in state.active_approvals
    assert state.active_approvals[target]["approval_id"] == "appr-test"
