"""T10 — invocation ack formatters + acting vs invoker identity."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_control.gitea_comments import format_fix_started
from agent_control.invocation_ack import (
    DEFAULT_ACTING_IDENTITY,
    append_identity_footer,
    format_invocation_started,
    format_invocation_terminal,
    identity_audit_from_parts,
    invoker_fields_from_trigger,
)
from agent_control.session import begin_typed_session
from agent_shared.models.jobs import TriggerContext


def test_format_invocation_started_includes_run_invoker_queue() -> None:
    body = format_invocation_started(
        command="review",
        run_id="run-abc",
        invoked_by="alice",
        session_id="sess-1",
        queue="rlm-root",
        host="ct104",
        invoked_by_id=42,
        source_comment_id=99,
        source_delivery_id="deliv-1",
    )
    assert "## Agent started (`review`)" in body
    assert "Run: `run-abc`" in body
    assert "Invoker: `alice`" in body
    assert "Queue: `rlm-root`" in body
    assert "Host: `ct104`" in body
    assert f"acting_identity: `{DEFAULT_ACTING_IDENTITY}`" in body
    assert "invoked_by: `alice`" in body
    assert "invoked_by_id: `42`" in body
    assert "source_comment_id: `99`" in body
    assert "source_delivery_id: `deliv-1`" in body
    assert "session_id: `sess-1`" in body


def test_format_invocation_terminal_failure_and_blocked() -> None:
    fail = format_invocation_terminal(
        outcome="failure",
        command="plan",
        run_id="run-x",
        invoked_by="bob",
        reason="sandbox unavailable",
        reason_code="sandbox_unavailable",
    )
    assert "## Agent failed (`plan`)" in fail
    assert "Outcome: **failure**" in fail
    assert "Reason code: `sandbox_unavailable`" in fail
    assert "run_id: `run-x`" in fail

    blocked = format_invocation_terminal(
        outcome="blocked",
        command="fix",
        run_id="run-y",
        invoked_by="bob",
        reason_code="policy_denied",
    )
    assert "## Agent blocked (`fix`)" in blocked
    assert "Outcome: **blocked**" in blocked


def test_append_identity_footer_idempotent() -> None:
    audit = identity_audit_from_parts(invoked_by="carol", run_id="run-1")
    once = append_identity_footer("## Hello", audit)
    twice = append_identity_footer(once, audit)
    assert once.count("acting_identity:") == 1
    assert twice == once


def test_format_fix_started_includes_identity_footer() -> None:
    body = format_fix_started(
        run_id="run-abc",
        approval_target_id="WI-0001",
        allowed_files=["README.md"],
        remote_publish_enabled=True,
        invoked_by="dave",
        session_id="sess-fix",
    )
    assert "V4.1.1 / 6D.2" in body
    assert "Invoker: `dave`" in body
    assert "Queue: `rlm-root`" in body
    assert f"acting_identity: `{DEFAULT_ACTING_IDENTITY}`" in body
    assert "invoked_by: `dave`" in body
    assert "run_id: `run-abc`" in body


def test_invoker_fields_from_trigger_dict_and_model() -> None:
    fields = invoker_fields_from_trigger(
        {"author": "erin", "author_id": "7", "comment_id": "55"},
        delivery_id="d-1",
    )
    assert fields["invoked_by"] == "erin"
    assert fields["invoked_by_id"] == 7
    assert fields["source_comment_id"] == 55
    assert fields["source_delivery_id"] == "d-1"

    tc = TriggerContext(
        event_type="gitea.issue_comment",
        issue_number=2,
        author="frank",
        author_id=11,
        comment_id="88",
        raw_body="/agent review",
        normalized_body="/agent review",
    )
    fields2 = invoker_fields_from_trigger(tc, delivery_id="d-2")
    assert fields2["invoked_by"] == "frank"
    assert fields2["invoked_by_id"] == 11
    assert fields2["source_comment_id"] == 88


def test_begin_session_sets_acting_vs_invoker(tmp_path: Path) -> None:
    state = tmp_path / "agent-state"
    state.mkdir()
    tc = TriggerContext(
        event_type="gitea.issue_comment",
        issue_number=2,
        author="grace",
        author_id=21,
        comment_id="100",
        raw_body="/agent review",
        normalized_body="/agent review",
    )
    session = begin_typed_session(
        state,
        project="ai-sdlc-lab/demo-app",
        command_kind="review",
        run_id="run-t10-1",
        head_sha="deadbeef",
        trigger_context=tc,
        source_delivery_id="delivery-t10",
    )
    assert session.invoked_by == "grace"
    assert session.invoked_by_id == 21
    assert session.source_comment_id == 100
    assert session.source_delivery_id == "delivery-t10"
    assert session.acting_identity == DEFAULT_ACTING_IDENTITY
    assert session.acting_identity != session.invoked_by


def test_dispatch_posts_started_ack_on_enqueue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agent_control.queue import EnqueueResult
    from agent_control.workflows.dispatch import maybe_dispatch_rlm_root
    from agent_shared.models.intent import CommandIntent
    from agent_shared.models.state import VerificationState
    from support.policy_pin import install_fake_policy_pin

    state = tmp_path / "agent-state"
    state.mkdir()
    monkeypatch.setenv("AGENT_STATE_ROOT", str(state))
    monkeypatch.setenv("AGENT_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("MODEL_ROUTING_POLICY", "fake")
    monkeypatch.setenv("GITEA_BOT_TOKEN", "tok")
    install_fake_policy_pin(monkeypatch)

    posted: list[str] = []

    def _enqueue(redis_url: str, payload: dict) -> EnqueueResult:
        return EnqueueResult(outcome="enqueued", job_id="rq-t10-1")

    def _capture(project, issue, body, settings=None):
        posted.append(body)
        return {"id": 1}

    monkeypatch.setattr("agent_control.queue.enqueue_rlm_root", _enqueue)
    monkeypatch.setattr("agent_control.gitea_comments.post_issue_comment", _capture)

    vs = VerificationState(
        project="ai-sdlc-lab/demo-app",
        command_intent=CommandIntent(
            activated=True,
            activation="/agent",
            kind="inspect",
            natural_language_task="hello",
            confidence=1.0,
        ),
        dispatch_recommended=True,
        dispatch_kind="inspect",
    )
    trigger = {
        "event_id": "evt-t10-ack",
        "delivery_id": "deliv-t10",
        "type": "gitea.issue_comment",
        "project": "ai-sdlc-lab/demo-app",
        "payload": {
            "issue": {"number": 3},
            "comment": {
                "id": 44,
                "body": "/agent inspect hello",
                "user": {"login": "helen", "id": 33},
            },
        },
    }
    result = maybe_dispatch_rlm_root(vs, trigger, "redis://localhost:6379/0")
    assert result.get("dispatched") is True
    assert posted, "expected started ack comment"
    body = posted[0]
    assert "Agent started (`inspect`)" in body
    assert "helen" in body
    assert result["run_id"] in body
    assert "acting_identity:" in body
    assert "invoked_by: `helen`" in body
