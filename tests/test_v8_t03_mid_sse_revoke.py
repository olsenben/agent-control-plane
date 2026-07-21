"""V8 T03 — mid-SSE Observatory shared-token revoke."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from agent_control.observe.auth import OBSERVE_SHARED_TOKEN_FILENAME
from agent_control.observe.events import append_control_decision
from agent_control.session.storage import persist_session_with_run_index
from agent_control.webhook_server import create_app
from agent_shared.models.agent_session import AgentSession, SessionStatus


def _seed(root: Path, project: str, run_id: str) -> None:
    session = AgentSession(
        session_id="sess-v8t03",
        project=project,
        repo=project.split("/", 1)[1],
        subject_kind="issue",
        subject_number=1,
        command_kind="plan",
        status=SessionStatus.QUEUED,
        run_ids=[run_id],
        correlation_id="corr-v8t03",
        trace_id="tr-v8t03",
        input_state_sha="a" * 64,
        head_sha="b" * 40,
        policy_source_sha="c" * 40,
        risk_level="risk1",
        invoked_by="v8t03",
        created_at="2026-07-21T00:00:00+00:00",
        updated_at="2026-07-21T00:00:00+00:00",
    )
    persist_session_with_run_index(root, session)
    append_control_decision(
        root,
        project=project,
        kind="other",
        summary="v8-t03-seed",
        session_id=session.session_id,
        run_id=run_id,
        trace_id=session.trace_id,
    )


def test_observe_sse_midstream_shared_token_file_revoke(
    tmp_path: Path, monkeypatch
) -> None:
    """Rotate .observe_shared_token between SSE poll ticks → forbidden error event."""
    monkeypatch.setenv("AGENT_STATE_ROOT", str(tmp_path))
    monkeypatch.setenv("OBSERVE_REQUIRE_AUTH", "true")
    monkeypatch.delenv("OBSERVE_SHARED_TOKEN", raising=False)

    project = "ai-sdlc-lab/demo-app"
    run_id = "run-v8t03"
    _seed(tmp_path, project, run_id)

    token_path = tmp_path / OBSERVE_SHARED_TOKEN_FILENAME
    token_path.write_text("token-v1\n", encoding="utf-8")

    ticks = {"n": 0}

    async def _sleep_rotate(_delay: float) -> None:
        ticks["n"] += 1
        if ticks["n"] == 1:
            # Mid-stream: invalidate shared token after first successful poll.
            token_path.write_text("token-v2-rotated\n", encoding="utf-8")

    monkeypatch.setattr("agent_control.observe.routes.asyncio.sleep", _sleep_rotate)

    app = create_app()
    client = TestClient(app)
    url = f"/api/observe/sessions/{run_id}/stream?project={project}"
    headers = {"Authorization": "Bearer token-v1"}

    with client.stream("GET", url, headers=headers) as resp:
        assert resp.status_code == 200
        body = resp.read()

    assert ticks["n"] >= 1
    assert b"data:" in body  # at least one event before revoke
    assert b"event: error" in body
    assert b"forbidden" in body
    err_at = body.find(b"event: error")
    assert b"\nid: " not in body[err_at:]


def test_observe_sse_midstream_settings_token_mutate(
    tmp_path: Path, monkeypatch
) -> None:
    """Mutating app.state.settings.observe_shared_token mid-stream also ends the stream."""
    monkeypatch.setenv("AGENT_STATE_ROOT", str(tmp_path))
    monkeypatch.setenv("OBSERVE_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OBSERVE_SHARED_TOKEN", "settings-v1")

    project = "ai-sdlc-lab/demo-app"
    run_id = "run-v8t03-settings"
    _seed(tmp_path, project, run_id)

    app_holder: dict = {}
    ticks = {"n": 0}

    async def _sleep_rotate(_delay: float) -> None:
        ticks["n"] += 1
        if ticks["n"] == 1:
            app_holder["app"].state.settings.observe_shared_token = "settings-v2"

    monkeypatch.setattr("agent_control.observe.routes.asyncio.sleep", _sleep_rotate)

    app = create_app()
    app_holder["app"] = app
    client = TestClient(app)
    url = f"/api/observe/sessions/{run_id}/stream?project={project}"
    headers = {"Authorization": "Bearer settings-v1"}

    with client.stream("GET", url, headers=headers) as resp:
        assert resp.status_code == 200
        body = resp.read()

    assert ticks["n"] >= 1
    assert b"event: error" in body
    assert b"forbidden" in body
