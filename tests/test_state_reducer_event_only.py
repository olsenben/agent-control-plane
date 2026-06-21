from agent_control.state_reducer import ReductionMode, reduce_event_only


def test_push_updates_head_sha() -> None:
    events = [
        {
            "type": "gitea.push",
            "payload": {"ref": "refs/heads/main", "after": "abc123"},
        }
    ]
    state = reduce_event_only(events, "ai-sdlc-lab/demo-app")
    assert state.head_sha == "abc123"
    assert state.reduction_mode == ReductionMode.EVENT_ONLY


def test_comment_sets_fix_intent() -> None:
    events = [
        {
            "type": "gitea.issue_comment",
            "payload": {"comment": {"body": "/agent fix WI-0004-dc0b71eb"}},
        }
    ]
    state = reduce_event_only(events, "ai-sdlc-lab/demo-app")
    assert state.command_intent is not None
    assert state.command_intent.kind == "fix"
    assert state.command_intent.approval_target == "WI-0004-dc0b71eb"


def test_finding_scoped_fix_not_activated() -> None:
    events = [
        {
            "type": "gitea.issue_comment",
            "payload": {"comment": {"body": "/agent fix F-1"}},
        }
    ]
    state = reduce_event_only(events, "ai-sdlc-lab/demo-app")
    assert state.command_intent is None


def test_pr_sync_requires_snapshot() -> None:
    events = [{"type": "gitea.pr_synchronized", "payload": {}}]
    state = reduce_event_only(events, "ai-sdlc-lab/demo-app")
    assert state.snapshot_required is True


def test_issue_opened_populates_issue_state() -> None:
    events = [
        {
            "type": "gitea.issue_opened",
            "payload": {"issue": {"number": 1, "title": "bug", "state": "open"}},
        }
    ]
    state = reduce_event_only(events, "ai-sdlc-lab/demo-app")
    assert state.issue_state["number"] == 1


def test_workflow_failed_sets_pipeline_status() -> None:
    events = [{"type": "gitea.workflow_failed", "payload": {}}]
    state = reduce_event_only(events, "ai-sdlc-lab/demo-app")
    assert state.pipeline_status == "failed"
