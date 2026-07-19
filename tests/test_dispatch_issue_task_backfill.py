"""Tests for issue_body_for_task and dispatch backfill."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from agent_control.graph.context_pack import compile_context_pack
from agent_control.workflows.dispatch import build_rlm_job
from agent_control.workflows.issue_task_backfill import issue_body_for_task, maybe_backfill_command_intent
from agent_shared.models.context_pack import ContextPack
from agent_shared.models.intent import CommandIntent
from agent_shared.models.jobs import TriggerContext
from agent_shared.models.review import BlastRadiusContext
from agent_shared.models.state import VerificationState
from support.policy_pin import install_fake_policy_pin


@pytest.fixture(autouse=True)
def _fake_policy_pin(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_policy_pin(monkeypatch)


@pytest.mark.parametrize(
    ("issue_text", "expected"),
    [
        ("# Title\n\nDo X", "Do X"),
        ("Do X", "Do X"),
        ("## Context\nDo X", "## Context\nDo X"),
        ("# Title only", "Title only"),
    ],
)
def test_issue_body_for_task(issue_text: str, expected: str) -> None:
    assert issue_body_for_task(issue_text) == expected


def test_issue_body_for_task_gitea_format() -> None:
    title = "Add hello.md"
    body = "Create hello.md with a greeting."
    issue_text = f"# {title}\n\n{body}".strip()
    assert issue_body_for_task(issue_text) == body


def test_maybe_backfill_command_intent_returns_copy() -> None:
    intent = CommandIntent(
        activated=True,
        activation="/agent",
        kind="plan",
        natural_language_task="",
        confidence=1.0,
    )
    pack = ContextPack(
        project="ai-sdlc-lab/demo-app",
        issue_text="# Title\n\nDo X",
    )
    result = maybe_backfill_command_intent(
        intent,
        kind="plan",
        context_pack=pack,
        issue_number=16,
    )
    assert result is not intent
    assert result.natural_language_task == "Do X"
    assert intent.natural_language_task == ""


def _bare_plan_state() -> VerificationState:
    return VerificationState(
        project="ai-sdlc-lab/demo-app",
        command_intent=CommandIntent(
            activated=True,
            activation="/agent",
            kind="plan",
            natural_language_task="",
            confidence=1.0,
        ),
        dispatch_recommended=True,
    )


def _issue_trigger() -> dict:
    return {
        "event_id": "evt-backfill",
        "delivery_id": "del-backfill",
        "type": "gitea.issue_comment",
        "project": "ai-sdlc-lab/demo-app",
        "payload": {
            "comment": {"body": "/agent plan", "id": 1},
            "issue": {"number": 16},
            "repository": {"full_name": "ai-sdlc-lab/demo-app"},
        },
    }


def _pack_with_issue_text(issue_text: str) -> ContextPack:
    return ContextPack(
        project="ai-sdlc-lab/demo-app",
        issue_number=16,
        issue_text=issue_text,
        blast_radius=BlastRadiusContext(),
    )


@patch("agent_control.workflows.dispatch.compile_context_pack")
def test_bare_plan_backfills_from_gitea_shaped_issue(mock_compile) -> None:
    mock_compile.return_value = _pack_with_issue_text("# Add hello.md\n\nCreate hello.md with a greeting.")
    job = build_rlm_job(_bare_plan_state(), _issue_trigger())
    assert job is not None
    assert job.command_intent.natural_language_task == "Create hello.md with a greeting."


@patch("agent_control.workflows.dispatch.compile_context_pack")
def test_bare_plan_title_only_issue(mock_compile) -> None:
    mock_compile.return_value = _pack_with_issue_text("# Title only")
    job = build_rlm_job(_bare_plan_state(), _issue_trigger())
    assert job is not None
    assert job.command_intent.natural_language_task == "Title only"


@patch("agent_control.workflows.dispatch.compile_context_pack")
def test_bare_plan_body_only_issue_text_not_stripped(mock_compile) -> None:
    mock_compile.return_value = _pack_with_issue_text("Do X")
    job = build_rlm_job(_bare_plan_state(), _issue_trigger())
    assert job is not None
    assert job.command_intent.natural_language_task == "Do X"


@patch("agent_control.workflows.dispatch.compile_context_pack")
def test_bare_plan_h2_heading_not_stripped(mock_compile) -> None:
    mock_compile.return_value = _pack_with_issue_text("## Context\nDo X")
    job = build_rlm_job(_bare_plan_state(), _issue_trigger())
    assert job is not None
    assert job.command_intent.natural_language_task == "## Context\nDo X"


@patch("agent_control.workflows.dispatch.compile_context_pack")
def test_bare_review_backfills(mock_compile) -> None:
    mock_compile.return_value = _pack_with_issue_text("# Review\n\nCheck dispatch.py")
    state = VerificationState(
        project="ai-sdlc-lab/demo-app",
        command_intent=CommandIntent(
            activated=True,
            activation="/agent",
            kind="review",
            natural_language_task="",
            confidence=1.0,
        ),
        dispatch_recommended=True,
    )
    trigger = {
        "event_id": "evt-review",
        "type": "gitea.issue_comment",
        "project": "ai-sdlc-lab/demo-app",
        "payload": {"comment": {"body": "/agent review"}, "issue": {"number": 16}},
    }
    job = build_rlm_job(state, trigger)
    assert job is not None
    assert job.command_intent.natural_language_task == "Check dispatch.py"


@patch("agent_control.workflows.dispatch.compile_context_pack")
def test_explicit_plan_task_wins(mock_compile) -> None:
    mock_compile.return_value = _pack_with_issue_text("# Title\n\nIssue body")
    state = VerificationState(
        project="ai-sdlc-lab/demo-app",
        command_intent=CommandIntent(
            activated=True,
            activation="/agent",
            kind="plan",
            natural_language_task="explicit task here",
            confidence=1.0,
        ),
        dispatch_recommended=True,
    )
    job = build_rlm_job(state, _issue_trigger())
    assert job is not None
    assert job.command_intent.natural_language_task == "explicit task here"


def test_inspect_does_not_backfill() -> None:
    state = VerificationState(
        project="ai-sdlc-lab/demo-app",
        command_intent=CommandIntent(
            activated=True,
            activation="/agent",
            kind="inspect",
            natural_language_task="",
            confidence=0.8,
        ),
        dispatch_recommended=True,
    )
    trigger = {
        "event_id": "evt-inspect",
        "type": "gitea.issue_comment",
        "project": "ai-sdlc-lab/demo-app",
        "payload": {"comment": {"body": "/agent inspect"}, "issue": {"number": 16}},
    }
    job = build_rlm_job(state, trigger)
    assert job is not None
    assert job.command_intent.natural_language_task == ""
    assert job.context_pack is None


@patch("agent_control.workflows.dispatch.compile_context_pack")
def test_plan_without_issue_number_no_backfill(mock_compile) -> None:
    mock_compile.return_value = _pack_with_issue_text("# Title\n\nBody")
    trigger = {
        "event_id": "evt-no-issue",
        "type": "gitea.pull_request_comment",
        "project": "ai-sdlc-lab/demo-app",
        "payload": {"comment": {"body": "/agent plan"}},
    }
    job = build_rlm_job(_bare_plan_state(), trigger)
    assert job is not None
    assert job.command_intent.natural_language_task == ""


def test_compile_context_pack_gitea_issue_text_shape(graph_settings) -> None:
    trigger = TriggerContext(event_type="test", issue_number=16)
    pack = compile_context_pack(
        "ai-sdlc-lab/agent-control-plane",
        trigger,
        settings=graph_settings,
        issue_override={"title": "Add hello.md", "body": "Create hello.md with a greeting."},
    )
    gitea_shaped = "# Add hello.md\n\nCreate hello.md with a greeting."
    assert issue_body_for_task(gitea_shaped) == "Create hello.md with a greeting."
    assert issue_body_for_task(pack.issue_text or "") == "Create hello.md with a greeting."
