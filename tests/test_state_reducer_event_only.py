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
            "payload": {"comment": {"body": "please /agent fix F-1"}},
        }
    ]
    state = reduce_event_only(events, "ai-sdlc-lab/demo-app")
    assert state.command_intent == "fix"


def test_pr_sync_requires_snapshot() -> None:
    events = [{"type": "gitea.pr_synchronized", "payload": {}}]
    state = reduce_event_only(events, "ai-sdlc-lab/demo-app")
    assert state.snapshot_required is True
