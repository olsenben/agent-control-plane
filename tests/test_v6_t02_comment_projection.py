"""V6 T02 — session comment projection."""

from __future__ import annotations

from agent_control.observe.comment_projection import (
    _should_apply_update,
    display_status_from_session,
    render_session_comment_body,
)
from agent_shared.models.agent_session import AgentSession, SessionStatus


def test_display_status_queued() -> None:
    session = AgentSession(
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
    assert display_status_from_session(session) == "queued"


def test_stale_sequence_rejected() -> None:
    session = AgentSession(
        session_id="sess-t02b",
        project="ai-sdlc-lab/demo-app",
        repo="demo-app",
        subject_kind="issue",
        subject_number=1,
        command_kind="review",
        status=SessionStatus.RUNNING,
        run_ids=["run-t02b"],
        correlation_id="corr-y",
        input_state_sha="abc",
        head_sha="def",
        risk_level="risk_1",
        invoked_by="bob",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        last_rendered_event_sequence=5,
        last_rendered_status="waiting_for_ci",
    )
    assert not _should_apply_update(session, event_sequence=3, display_status="running")


def test_render_includes_identity_footer() -> None:
    session = AgentSession(
        session_id="sess-t02c",
        project="ai-sdlc-lab/demo-app",
        repo="demo-app",
        subject_kind="issue",
        subject_number=1,
        command_kind="review",
        status=SessionStatus.QUEUED,
        run_ids=["run-t02c"],
        correlation_id="corr-z",
        input_state_sha="abc",
        head_sha="def",
        risk_level="risk_1",
        invoked_by="carol",
        acting_identity="agent-bot",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    body = render_session_comment_body(
        session=session,
        run_id="run-t02c",
        display_status="queued",
        command="review",
    )
    assert "acting_identity: `agent-bot`" in body
    assert "Invoker: `carol`" in body or "invoked_by: `carol`" in body
