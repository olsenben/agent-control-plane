"""V6 T02 — session comment projection + status FSM."""

from __future__ import annotations

from agent_control.observe.comment_projection import (
    _should_apply_update,
    display_status_from_session,
    render_session_comment_body,
    transition_allowed,
)
from agent_shared.models.agent_session import AgentSession, SessionStatus


def _session(**kwargs):
    base = dict(
        session_id="sess-t02",
        project="ai-sdlc-lab/demo-app",
        repo="demo-app",
        subject_kind="issue",
        subject_number=1,
        command_kind="review",
        status=SessionStatus.QUEUED,
        run_ids=["run-t02"],
        correlation_id="corr-x",
        input_state_sha="abc",
        head_sha="def",
        risk_level="risk_1",
        invoked_by="alice",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    base.update(kwargs)
    return AgentSession(**base)


def test_display_status_queued() -> None:
    assert display_status_from_session(_session()) == "queued"


def test_fsm_allowed_and_forbidden_transitions() -> None:
    assert transition_allowed("queued", "running")
    assert transition_allowed("running", "waiting_for_ci")
    assert transition_allowed("waiting_for_ci", "verified")
    assert transition_allowed("waiting_for_ci", "verification_missing")
    assert not transition_allowed("queued", "waiting_for_ci")
    assert not transition_allowed("verified", "running")
    assert not transition_allowed("failed", "completed")


def test_stale_sequence_rejected() -> None:
    session = _session(
        session_id="sess-t02b",
        status=SessionStatus.RUNNING,
        run_ids=["run-t02b"],
        correlation_id="corr-y",
        invoked_by="bob",
        last_rendered_event_sequence=5,
        last_rendered_status="waiting_for_ci",
    )
    assert not _should_apply_update(session, event_sequence=3, display_status="running")


def test_forbidden_transition_rejected_even_with_newer_sequence() -> None:
    session = _session(
        status=SessionStatus.RUNNING,
        last_rendered_event_sequence=5,
        last_rendered_status="verified",
    )
    assert not _should_apply_update(session, event_sequence=6, display_status="running")


def test_render_includes_identity_footer() -> None:
    session = _session(
        session_id="sess-t02c",
        run_ids=["run-t02c"],
        correlation_id="corr-z",
        invoked_by="carol",
        acting_identity="agent-bot",
    )
    body = render_session_comment_body(
        session=session,
        run_id="run-t02c",
        display_status="queued",
        command="review",
    )
    assert "acting_identity: `agent-bot`" in body
    assert "Invoker: `carol`" in body or "invoked_by: `carol`" in body
