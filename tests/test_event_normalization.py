"""Gitea webhook event type normalization."""

from agent_control.event_types import canonical_gitea_event_type


def test_issue_comment_from_ledger_shape() -> None:
    payload = {
        "action": "created",
        "issue": {"number": 1, "title": "test"},
        "comment": {"body": "test"},
        "repository": {"full_name": "ai-sdlc-lab/agent-control-plane"},
    }
    canonical, action = canonical_gitea_event_type("issue_comment", payload)
    assert canonical == "gitea.issue_comment"
    assert action == "created"


def test_issue_label_maps_to_labeled() -> None:
    payload = {"label": {"name": "agent:review"}, "issue": {"number": 1}}
    canonical, _ = canonical_gitea_event_type("issue_label", payload)
    assert canonical == "gitea.issue_labeled"


def test_pull_request_sync() -> None:
    payload = {"pull_request": {"number": 2}}
    canonical, _ = canonical_gitea_event_type("pull_request_sync", payload)
    assert canonical == "gitea.pr_synchronized"


def test_workflow_run_passed() -> None:
    payload = {
        "workflow_run": {"status": "completed", "conclusion": "success"},
    }
    canonical, _ = canonical_gitea_event_type("workflow_run", payload)
    assert canonical == "gitea.workflow_passed"


def test_workflow_run_failed() -> None:
    payload = {
        "workflow_run": {"status": "completed", "conclusion": "failure"},
    }
    canonical, _ = canonical_gitea_event_type("workflow_run", payload)
    assert canonical == "gitea.workflow_failed"


def test_workflow_run_started() -> None:
    payload = {"workflow_run": {"status": "in_progress"}}
    canonical, _ = canonical_gitea_event_type("workflow_run", payload)
    assert canonical == "gitea.workflow_started"
