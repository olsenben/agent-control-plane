"""V8 T03 -- mid-SSE Observatory shared-token revoke.

Updated for V9 T03 (protected SSE subscribe-first + Redis id-notify, H4):
the SSE generator no longer polls on a fixed ``asyncio.sleep`` cadence --
each iteration of the live-tail loop blocks (off the event loop) on
``pubsub.get_message(timeout=...)`` instead. These tests now hook that call
via a fake Redis pubsub to rotate the shared token "mid-stream" (between the
initial history replay and the live-tail loop's first auth re-check),
exercising the same invariant V8 T03 established: a permission revoke that
happens while an SSE connection is open must end that stream with
``event: error`` / "forbidden", never silently keep streaming under a
now-invalid credential.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

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


class _RevokeOnFirstPollPubSub:
    """Fake ``redis.client.PubSub``: no live notifies, but the *first* live-tail
    poll tick runs ``on_first_poll`` -- used to rotate/mutate credentials
    exactly between the history replay and the loop's next auth re-check,
    mirroring what the old ``asyncio.sleep`` tick hook used to simulate.
    """

    def __init__(self, on_first_poll) -> None:
        self._on_first_poll = on_first_poll
        self._calls = 0

    def subscribe(self, _channel: str) -> None:
        return None

    def get_message(self, timeout=None):
        self._calls += 1
        if self._calls == 1:
            self._on_first_poll()
        return None

    def close(self) -> None:
        return None


class _FakeRedisClient:
    def __init__(self, pubsub) -> None:
        self._pubsub = pubsub

    def pubsub(self):
        return self._pubsub

    def publish(self, _channel: str, _message: str) -> None:
        # The seed control_decision below also goes through the real
        # projector -> notify path; without this no-op, that publish call
        # would raise (this fake has no real socket), which would trip the
        # notify circuit breaker for this test's redis_url and make the SSE
        # call below see it as already-open (degraded before ever calling
        # our patched subscribe()).
        return None

    def close(self) -> None:
        return None


def test_observe_sse_midstream_shared_token_file_revoke(
    tmp_path: Path, monkeypatch
) -> None:
    """Rotate .observe_shared_token mid-stream -> forbidden error event."""
    monkeypatch.setenv("AGENT_STATE_ROOT", str(tmp_path))
    monkeypatch.setenv("OBSERVE_REQUIRE_AUTH", "true")
    monkeypatch.delenv("OBSERVE_SHARED_TOKEN", raising=False)
    # Unique per test so the module-level notify circuit breaker
    # (agent_control.observe.notify) never leaks state from another test's
    # real connection failure into this one's mocked redis.
    monkeypatch.setenv("REDIS_URL", f"redis://fake-{tmp_path.name}:6379/0")

    project = "ai-sdlc-lab/demo-app"
    run_id = "run-v8t03"

    token_path = tmp_path / OBSERVE_SHARED_TOKEN_FILENAME
    token_path.write_text("token-v1\n", encoding="utf-8")

    def _rotate() -> None:
        token_path.write_text("token-v2-rotated\n", encoding="utf-8")

    fake_client = _FakeRedisClient(_RevokeOnFirstPollPubSub(_rotate))

    app = create_app()
    client = TestClient(app)
    url = f"/api/observe/sessions/{run_id}/stream?project={project}"
    headers = {"Authorization": "Bearer token-v1"}

    # Seeding (which projects through the real notify-publish path) must
    # also see the patched redis client -- otherwise its publish attempt
    # hits a real, unreachable host and trips the circuit breaker for this
    # test's redis_url before the SSE call below ever runs.
    with patch("redis.Redis.from_url", return_value=fake_client):
        _seed(tmp_path, project, run_id)
        with client.stream("GET", url, headers=headers) as resp:
            assert resp.status_code == 200
            body = resp.read()

    assert b"data:" in body  # at least one event (history) before revoke
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
    monkeypatch.setenv("REDIS_URL", f"redis://fake-{tmp_path.name}:6379/0")

    project = "ai-sdlc-lab/demo-app"
    run_id = "run-v8t03-settings"

    app = create_app()

    def _mutate() -> None:
        app.state.settings.observe_shared_token = "settings-v2"

    fake_client = _FakeRedisClient(_RevokeOnFirstPollPubSub(_mutate))

    client = TestClient(app)
    url = f"/api/observe/sessions/{run_id}/stream?project={project}"
    headers = {"Authorization": "Bearer settings-v1"}

    with patch("redis.Redis.from_url", return_value=fake_client):
        _seed(tmp_path, project, run_id)
        with client.stream("GET", url, headers=headers) as resp:
            assert resp.status_code == 200
            body = resp.read()

    assert b"event: error" in body
    assert b"forbidden" in body
