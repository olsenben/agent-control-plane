"""V6 T07 NL invocation + clarification lifecycle."""

from __future__ import annotations

from pathlib import Path

from agent_control.intent_parser import parse_command_intent
from agent_control.invocation import begin_invocation, request_clarification
from agent_control.nl_intent import extract_agent_intent, is_bare_at_agent
from agent_control.state_reducer import dispatch_for_comment_body


def test_slash_agent_review_unchanged() -> None:
    intent, dispatch, kind = dispatch_for_comment_body("/agent review")
    assert intent.activated is True
    assert intent.kind == "review"
    assert intent.activation == "/agent"
    assert dispatch is True
    assert kind == "review"


def test_no_at_agent_prefix_no_dispatch() -> None:
    intent, dispatch, _ = dispatch_for_comment_body("please explain why CI fails")
    assert intent.activated is False
    assert dispatch is False


def test_at_agent_explain_ci_resolves() -> None:
    intent = parse_command_intent("@agent explain why CI fails")
    assert intent.activated is True
    assert intent.kind == "explain"
    assert intent.activation == "@agent"
    assert "CI" in intent.natural_language_task or "ci" in intent.natural_language_task.lower()
    assert intent.confidence >= 0.7


def test_ambiguous_at_agent_requests_clarification(tmp_path: Path) -> None:
    body = "@agent do the thing with the stuff"
    assert is_bare_at_agent(body)
    agent_intent = extract_agent_intent(body)
    assert agent_intent.kind is None or agent_intent.confidence < 0.7
    record = begin_invocation(
        tmp_path,
        project="ai-sdlc-lab/demo-app",
        raw_text=body,
        invoked_by="alice",
        intent=agent_intent,
    )
    assert record.status in ("intent_ambiguous", "invocation_received")
    clarified = request_clarification(tmp_path, record)
    assert clarified.status == "clarification_requested"
    assert clarified.invocation_id.startswith("inv-")


def test_semantic_router_not_default() -> None:
    import os

    assert os.environ.get("NL_INTENT_BACKEND", "heuristic") in ("heuristic", "instructor", "semantic_router")
    # Day-one default path uses heuristic extractor.
    intent = extract_agent_intent("@agent review the latest pull request")
    assert intent.extractor == "heuristic"
    assert intent.kind == "review"
