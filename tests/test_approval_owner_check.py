"""Approval authority: namespace owner, GITEA_APPROVER_LOGINS, handler feedback."""

from pathlib import Path
from unittest.mock import patch

import pytest

from agent_control.approval.handlers import handle_approval_commands
from agent_control.approval.storage import load_approval
from agent_control.config import Settings
from agent_control.events import AgentEvent, append_event
from agent_control.intent_parser import parse_command_intent
from agent_control.jobs.state import process_state_reduction
from agent_control.project_registry import build_trigger_context, is_approval_authority
from conftest import seed_plan_completed

PROJECT = "ai-sdlc-lab/agent-control-plane"


def test_namespace_owner_is_approval_authority() -> None:
    assert is_approval_authority("ai-sdlc-lab", PROJECT) is True
    assert is_approval_authority("olsenben", PROJECT) is False


def test_gitea_approver_logins_grant_authority(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITEA_APPROVER_LOGINS", "olsenben,other-admin")
    settings = Settings()
    assert is_approval_authority("olsenben", PROJECT, settings=settings) is True
    assert is_approval_authority("other-admin", PROJECT, settings=settings) is True
    assert is_approval_authority("random-user", PROJECT, settings=settings) is False


def test_build_trigger_context_marks_configured_approver_as_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITEA_APPROVER_LOGINS", "olsenben")
    event = {
        "type": "gitea.issue_comment",
        "project": PROJECT,
        "payload": {
            "comment": {"id": 9001, "body": "/agent approve WI-0006-d4c92e62", "user": {"login": "olsenben"}},
            "issue": {"number": 6},
        },
    }
    tc = build_trigger_context(event, "/agent approve WI-0006-d4c92e62", settings=Settings())
    assert tc["author_is_owner"] is True


def test_non_owner_approve_posts_rejection_comment(tmp_path: Path) -> None:
    target = seed_plan_completed(tmp_path, issue_id=6, run_id="run-c29ad349c1f560bc6b989732d4c92e62")
    trigger = {
        "type": "gitea.issue_comment",
        "project": PROJECT,
        "payload": {
            "comment": {
                "id": 9100,
                "body": f"/agent approve {target}",
                "user": {"login": "random-user"},
            },
            "issue": {"number": 6},
        },
    }
    intent = parse_command_intent(f"/agent approve {target}")
    posted: list[str] = []

    with patch("agent_control.approval.handlers.post_issue_comment", side_effect=lambda *a, **k: posted.append(a[2])):
        result = handle_approval_commands(tmp_path, PROJECT, trigger, intent)

    assert result["handled"] is True
    assert result["created"] is False
    assert load_approval(tmp_path, PROJECT, target) is None
    assert posted
    assert "Owner approval required" in posted[0]


def test_configured_approver_grants_via_state_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITEA_APPROVER_LOGINS", "olsenben")
    target = seed_plan_completed(tmp_path, issue_id=6, run_id="run-c29ad349c1f560bc6b989732d4c92e62")
    event = AgentEvent(
        event_id="evt-approve-6",
        type="gitea.issue_comment",
        raw_event_type="issue_comment",
        project=PROJECT,
        recorded_at="2026-06-21T21:00:00+00:00",
        payload={
            "comment": {
                "id": 9200,
                "body": f"/agent approve {target}",
                "user": {"login": "olsenben"},
            },
            "issue": {"number": 6},
        },
    )
    append_event(tmp_path, event)
    posted: list[str] = []

    with patch("agent_control.approval.handlers.post_issue_comment", side_effect=lambda *a, **k: posted.append(a[2])):
        result = process_state_reduction(str(tmp_path), "evt-approve-6", PROJECT)

    assert result["approval"]["handled"] is True
    assert result["approval"]["created"] is True
    stored = load_approval(tmp_path, PROJECT, target)
    assert stored is not None
    assert stored.approved_by_login == "olsenben"
    assert posted
    assert "Approval granted" in posted[0]
