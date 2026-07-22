"""V9 T03 -- protected SSE subscribe-first + Redis id-notify + Last-Event-ID.

Covers the H4 protected-SSE contract end-to-end:

1. Authorize before the stream opens (never a 200 + streamed error).
2. Subscribe to the per-run Redis notify channel FIRST, before any
   observe.sqlite history read.
3. Emit every observe.sqlite row with ``projection_sequence > after``
   (``after`` = ``Last-Event-ID`` / ``?after_sequence=``, whichever is
   higher).
4. Drain Redis notifications for as long as the client stays connected.
5. For each notification: never trust its payload as display data -- always
   re-read observe.sqlite and dedupe by ``projection_sequence``.
6. Redis outage degrades live tailing only; history stays complete.

Uses ``tests/_fake_redis.py`` (an in-process fake Redis pub/sub) since real
Redis is never available in this test environment; both the projector's
notify publish and the route's subscribe patch the same
``redis.Redis.from_url`` so a real end-to-end publish/subscribe round trip
can be exercised without a live server.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.requests import Request

from agent_control.observe.events import append_control_decision
from agent_control.observe.notify import notify_channel
from agent_control.observe.store import ObserveStore
from agent_control.session.storage import persist_session_with_run_index
from agent_control.webhook_server import create_app
from agent_shared.models.agent_session import AgentSession, SessionStatus

from _fake_redis import FakeRedisBroker, disconnect_after, fake_redis_from_url

PROJECT = "ai-sdlc-lab/demo-app"


def _seed_session(root: Path, run_id: str, session_id: str) -> None:
    session = AgentSession(
        session_id=session_id,
        project=PROJECT,
        repo=PROJECT.split("/", 1)[1],
        subject_kind="issue",
        subject_number=1,
        command_kind="plan",
        status=SessionStatus.QUEUED,
        run_ids=[run_id],
        correlation_id=f"corr-{session_id}",
        trace_id=f"tr-{session_id}",
        input_state_sha="a" * 64,
        head_sha="b" * 40,
        policy_source_sha="c" * 40,
        risk_level="risk1",
        invoked_by="tester",
        created_at="2026-07-22T00:00:00+00:00",
        updated_at="2026-07-22T00:00:00+00:00",
    )
    persist_session_with_run_index(root, session)


def _seed_event(root: Path, *, run_id: str, session_id: str, summary: str) -> None:
    append_control_decision(
        root,
        project=PROJECT,
        kind="other",
        summary=summary,
        session_id=session_id,
        run_id=run_id,
        trace_id=f"tr-{session_id}",
    )


def _app(tmp_path: Path, monkeypatch, **env):
    monkeypatch.setenv("AGENT_STATE_ROOT", str(tmp_path))
    monkeypatch.setenv("OBSERVE_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OBSERVE_SHARED_TOKEN", "shared-v9t03")
    # Unique per test so agent_control.observe.notify's module-level,
    # per-redis_url circuit breaker can never leak an open-circuit state
    # from one test's real (unreachable-host) failure into another test
    # that expects a working (faked) redis.Redis.from_url. Without this,
    # any *unmocked* notify publish before the test's patch context is
    # entered (e.g. seeding via append_control_decision) would trip the
    # breaker for the shared default redis_url and make every later test
    # in this module see the circuit already open -- degraded before
    # redis.Redis.from_url is ever called, bypassing the fake entirely.
    monkeypatch.setenv("REDIS_URL", f"redis://fake-{tmp_path.name}:6379/0")
    monkeypatch.delenv("OBSERVE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("OBSERVE_OAUTH_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("OBSERVE_OAUTH_REDIRECT_URI", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return create_app()


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer shared-v9t03"}


def _frames(body: bytes) -> list[tuple[str | None, str | None, dict | None]]:
    """Parse raw SSE bytes into ``(event, id, data_dict)`` tuples, one per frame."""
    text = body.decode("utf-8")
    out: list[tuple[str | None, str | None, dict | None]] = []
    for chunk in text.split("\n\n"):
        chunk = chunk.strip("\n")
        if not chunk:
            continue
        event = None
        frame_id = None
        data = None
        for line in chunk.split("\n"):
            if line.startswith("event:"):
                event = line[len("event:") :].strip()
            elif line.startswith("id:"):
                frame_id = line[len("id:") :].strip()
            elif line.startswith("data:"):
                raw = line[len("data:") :].strip()
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    data = None
        out.append((event, frame_id, data))
    return out


# --- H4 step 1: authorize before stream (still enforced with the new impl) --


def test_sse_unauthorized_never_returns_200(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch, OBSERVE_SHARED_TOKEN="shared-v9t03")
    _seed_session(tmp_path, "run-unauth", "sess-unauth")
    client = TestClient(app)
    with client.stream(
        "GET",
        "/api/observe/v1/sessions/run-unauth/stream",
        headers={"Accept": "text/event-stream"},
    ) as resp:
        assert resp.status_code == 401
        body = resp.read()
    assert b"event:" not in body


# --- H4 step 2: subscribe before history read -------------------------------


def test_subscribe_happens_before_history_read(tmp_path, monkeypatch) -> None:
    run_id, session_id = "run-order", "sess-order"
    _seed_session(tmp_path, run_id, session_id)
    _seed_event(tmp_path, run_id=run_id, session_id=session_id, summary="first")
    app = _app(tmp_path, monkeypatch)

    order: list[str] = []
    original_list = ObserveStore.list_events_for_run

    def _tracked_list(self, run_id_arg, **kwargs):
        order.append("history_read")
        return original_list(self, run_id_arg, **kwargs)

    monkeypatch.setattr(ObserveStore, "list_events_for_run", _tracked_list)

    broker = FakeRedisBroker()
    broker.on_subscribe = lambda _channel: order.append("subscribe")

    client = TestClient(app)
    with patch("redis.Redis.from_url", fake_redis_from_url(broker)):
        with patch.object(Request, "is_disconnected", disconnect_after(0)):
            with client.stream(
                "GET", f"/api/observe/v1/sessions/{run_id}/stream", headers=_headers()
            ) as resp:
                assert resp.status_code == 200
                resp.read()

    assert order[:2] == ["subscribe", "history_read"]


# --- H4 step 3: history, cursor = max(Last-Event-ID, ?after_sequence=) ------


def test_history_emitted_with_durable_sequence_ids(tmp_path, monkeypatch) -> None:
    run_id, session_id = "run-hist", "sess-hist"
    _seed_session(tmp_path, run_id, session_id)
    _seed_event(tmp_path, run_id=run_id, session_id=session_id, summary="one")
    _seed_event(tmp_path, run_id=run_id, session_id=session_id, summary="two")
    app = _app(tmp_path, monkeypatch)
    broker = FakeRedisBroker()

    client = TestClient(app)
    with patch("redis.Redis.from_url", fake_redis_from_url(broker)):
        with patch.object(Request, "is_disconnected", disconnect_after(0)):
            with client.stream(
                "GET", f"/api/observe/v1/sessions/{run_id}/stream", headers=_headers()
            ) as resp:
                assert resp.status_code == 200
                body = resp.read()

    frames = _frames(body)
    data_frames = [f for f in frames if f[1] is not None]
    assert [f[1] for f in data_frames] == ["1", "2"]
    for _event, frame_id, data in data_frames:
        assert data["sequence"] == int(frame_id)


def test_after_sequence_query_alias_filters_history(tmp_path, monkeypatch) -> None:
    run_id, session_id = "run-afterseq", "sess-afterseq"
    _seed_session(tmp_path, run_id, session_id)
    _seed_event(tmp_path, run_id=run_id, session_id=session_id, summary="one")
    _seed_event(tmp_path, run_id=run_id, session_id=session_id, summary="two")
    app = _app(tmp_path, monkeypatch)
    broker = FakeRedisBroker()

    client = TestClient(app)
    with patch("redis.Redis.from_url", fake_redis_from_url(broker)):
        with patch.object(Request, "is_disconnected", disconnect_after(0)):
            with client.stream(
                "GET",
                f"/api/observe/v1/sessions/{run_id}/stream?after_sequence=1",
                headers=_headers(),
            ) as resp:
                body = resp.read()

    ids = [fid for _e, fid, _d in _frames(body) if fid is not None]
    assert ids == ["2"]


def test_last_event_id_header_used_as_cursor(tmp_path, monkeypatch) -> None:
    run_id, session_id = "run-leid", "sess-leid"
    _seed_session(tmp_path, run_id, session_id)
    _seed_event(tmp_path, run_id=run_id, session_id=session_id, summary="one")
    _seed_event(tmp_path, run_id=run_id, session_id=session_id, summary="two")
    _seed_event(tmp_path, run_id=run_id, session_id=session_id, summary="three")
    app = _app(tmp_path, monkeypatch)
    broker = FakeRedisBroker()

    client = TestClient(app)
    headers = {**_headers(), "Last-Event-ID": "2"}
    with patch("redis.Redis.from_url", fake_redis_from_url(broker)):
        with patch.object(Request, "is_disconnected", disconnect_after(0)):
            with client.stream(
                "GET", f"/api/observe/v1/sessions/{run_id}/stream", headers=headers
            ) as resp:
                body = resp.read()

    ids = [fid for _e, fid, _d in _frames(body) if fid is not None]
    assert ids == ["3"]


def test_last_event_id_and_after_sequence_take_the_higher(tmp_path, monkeypatch) -> None:
    run_id, session_id = "run-max", "sess-max"
    _seed_session(tmp_path, run_id, session_id)
    for i in range(4):
        _seed_event(tmp_path, run_id=run_id, session_id=session_id, summary=f"n{i}")
    app = _app(tmp_path, monkeypatch)
    broker = FakeRedisBroker()

    client = TestClient(app)
    # Last-Event-ID says 1, ?after_sequence= says 3 -- must take 3 (the higher).
    headers = {**_headers(), "Last-Event-ID": "1"}
    with patch("redis.Redis.from_url", fake_redis_from_url(broker)):
        with patch.object(Request, "is_disconnected", disconnect_after(0)):
            with client.stream(
                "GET",
                f"/api/observe/v1/sessions/{run_id}/stream?after_sequence=3",
                headers=headers,
            ) as resp:
                body = resp.read()

    ids = [fid for _e, fid, _d in _frames(body) if fid is not None]
    assert ids == ["4"]


# --- Redis outage degrades live tailing only; history stays complete -------


def test_redis_outage_degrades_live_only_history_complete(tmp_path, monkeypatch) -> None:
    run_id, session_id = "run-outage", "sess-outage"
    _seed_session(tmp_path, run_id, session_id)
    _seed_event(tmp_path, run_id=run_id, session_id=session_id, summary="one")
    _seed_event(tmp_path, run_id=run_id, session_id=session_id, summary="two")
    app = _app(tmp_path, monkeypatch)

    client = TestClient(app)
    with patch("redis.Redis.from_url", side_effect=ConnectionError("redis down")):
        with client.stream(
            "GET", f"/api/observe/v1/sessions/{run_id}/stream", headers=_headers()
        ) as resp:
            assert resp.status_code == 200
            body = resp.read()

    frames = _frames(body)
    ids = [fid for _e, fid, _d in frames if fid is not None]
    assert ids == ["1", "2"]
    events = [e for e, _fid, _d in frames]
    assert "degraded" in events
    assert "end" in events
    # Degraded outage ends the stream promptly -- no live-loop frames after it.
    assert events.index("degraded") == len(events) - 2
    assert events[-1] == "end"


# --- H4 step 4/5: live notify -> re-read authoritative row; dedupe ----------


def test_notify_delivers_new_row_not_present_in_history(tmp_path, monkeypatch) -> None:
    run_id, session_id = "run-live", "sess-live"
    _seed_session(tmp_path, run_id, session_id)

    app = _app(tmp_path, monkeypatch)
    broker = FakeRedisBroker()

    def _write_second_row():
        _seed_event(tmp_path, run_id=run_id, session_id=session_id, summary="live-row")

    broker.next_first_poll_hook = _write_second_row

    client = TestClient(app)
    with patch("redis.Redis.from_url", fake_redis_from_url(broker)):
        with patch.object(Request, "is_disconnected", disconnect_after(1)):
            with client.stream(
                "GET", f"/api/observe/v1/sessions/{run_id}/stream", headers=_headers()
            ) as resp:
                assert resp.status_code == 200
                body = resp.read()

    frames = _frames(body)
    ids = [fid for _e, fid, _d in frames if fid is not None]
    # Nothing existed at history-drain time (session seeded, no events yet);
    # the row appears exactly once, delivered live via the notify.
    assert ids == ["1"]
    assert broker.publish_log  # the projector really did publish a notify


def test_duplicate_notify_for_already_delivered_row_is_not_reemitted(tmp_path, monkeypatch) -> None:
    run_id, session_id = "run-dedupe", "sess-dedupe"
    _seed_session(tmp_path, run_id, session_id)

    app = _app(tmp_path, monkeypatch)
    broker = FakeRedisBroker()
    channel = notify_channel(run_id)

    def _write_then_duplicate_notify():
        _seed_event(tmp_path, run_id=run_id, session_id=session_id, summary="only-row")
        # A second, duplicate ids-only notify for the exact same row (Redis
        # pub/sub is at-most-once per subscriber in reality, but a producer
        # retry or a second observer process could still emit two notifies
        # for one committed row) -- must not produce a second frame.
        broker.publish(channel, json.dumps({"run_id": run_id, "projection_sequence": 1, "observation_id": 1}))

    broker.next_first_poll_hook = _write_then_duplicate_notify

    client = TestClient(app)
    with patch("redis.Redis.from_url", fake_redis_from_url(broker)):
        with patch.object(Request, "is_disconnected", disconnect_after(2)):
            with client.stream(
                "GET", f"/api/observe/v1/sessions/{run_id}/stream", headers=_headers()
            ) as resp:
                body = resp.read()

    frames = _frames(body)
    ids = [fid for _e, fid, _d in frames if fid is not None]
    assert ids == ["1"]


def test_notify_payload_sequence_is_never_trusted_directly(tmp_path, monkeypatch) -> None:
    """A notify claiming a bogus/nonexistent ``projection_sequence`` must never
    produce a frame for that fabricated id -- the endpoint always re-reads
    observe.sqlite and only ever emits rows that actually exist there."""
    run_id, session_id = "run-untrusted", "sess-untrusted"
    _seed_session(tmp_path, run_id, session_id)

    app = _app(tmp_path, monkeypatch)
    broker = FakeRedisBroker()
    channel = notify_channel(run_id)

    def _bogus_notify_then_real_row():
        # Bogus notify naming a sequence that does not exist yet.
        broker.publish(
            channel, json.dumps({"run_id": run_id, "projection_sequence": 999, "observation_id": 999})
        )
        # The real, authoritative row.
        _seed_event(tmp_path, run_id=run_id, session_id=session_id, summary="authoritative-row")

    broker.next_first_poll_hook = _bogus_notify_then_real_row

    client = TestClient(app)
    with patch("redis.Redis.from_url", fake_redis_from_url(broker)):
        with patch.object(Request, "is_disconnected", disconnect_after(1)):
            with client.stream(
                "GET", f"/api/observe/v1/sessions/{run_id}/stream", headers=_headers()
            ) as resp:
                body = resp.read()

    frames = _frames(body)
    ids = [fid for _e, fid, _d in frames if fid is not None]
    # Only the real row (sequence 1) is ever emitted -- never "999".
    assert ids == ["1"]


def test_notify_for_a_different_run_id_is_ignored(tmp_path, monkeypatch) -> None:
    run_id, session_id = "run-mine", "sess-mine"
    other_run_id = "run-other"
    _seed_session(tmp_path, run_id, session_id)

    app = _app(tmp_path, monkeypatch)
    broker = FakeRedisBroker()
    channel = notify_channel(run_id)  # same channel this stream is subscribed to

    def _deliver_mismatched_run_id():
        # Same channel, but a payload naming a different run_id -- the
        # defensive check in the route must ignore it (belt-and-suspenders;
        # channels are already per-run_id in normal operation).
        broker.publish(
            channel,
            json.dumps({"run_id": other_run_id, "projection_sequence": 1, "observation_id": 1}),
        )

    broker.next_first_poll_hook = _deliver_mismatched_run_id

    client = TestClient(app)
    with patch("redis.Redis.from_url", fake_redis_from_url(broker)):
        with patch.object(Request, "is_disconnected", disconnect_after(1)):
            with client.stream(
                "GET", f"/api/observe/v1/sessions/{run_id}/stream", headers=_headers()
            ) as resp:
                body = resp.read()

    frames = _frames(body)
    ids = [fid for _e, fid, _d in frames if fid is not None]
    assert ids == []


def test_race_write_lands_exactly_at_subscribe_time_is_seen_exactly_once(tmp_path, monkeypatch) -> None:
    """H4's core race: a row committed (and its notify published) in the
    narrow window right as the stream subscribes must be captured -- via
    the history read that happens right after subscribe -- exactly once,
    even though its notify is *also* sitting in the queue by then."""
    run_id, session_id = "run-race", "sess-race"
    _seed_session(tmp_path, run_id, session_id)

    app = _app(tmp_path, monkeypatch)
    broker = FakeRedisBroker()

    def _write_right_at_subscribe(_channel: str) -> None:
        _seed_event(tmp_path, run_id=run_id, session_id=session_id, summary="raced-in")

    broker.on_subscribe = _write_right_at_subscribe

    client = TestClient(app)
    with patch("redis.Redis.from_url", fake_redis_from_url(broker)):
        with patch.object(Request, "is_disconnected", disconnect_after(1)):
            with client.stream(
                "GET", f"/api/observe/v1/sessions/{run_id}/stream", headers=_headers()
            ) as resp:
                body = resp.read()

    frames = _frames(body)
    ids = [fid for _e, fid, _d in frames if fid is not None]
    # Seen once (via history), never a second time (the notify that also
    # arrived for the same row must be deduped by projection_sequence).
    assert ids == ["1"]


def test_pending_notify_queued_before_subscribe_is_deduped_against_history(tmp_path, monkeypatch) -> None:
    run_id, session_id = "run-pending", "sess-pending"
    _seed_session(tmp_path, run_id, session_id)
    _seed_event(tmp_path, run_id=run_id, session_id=session_id, summary="already-there")

    app = _app(tmp_path, monkeypatch)
    broker = FakeRedisBroker()
    channel = notify_channel(run_id)
    # A notify for the row that already exists, queued so it is delivered
    # the instant this stream subscribes -- models a notify that was
    # in-flight before the subscription existed.
    broker.queue_pending(channel, json.dumps({"run_id": run_id, "projection_sequence": 1, "observation_id": 1}))

    client = TestClient(app)
    with patch("redis.Redis.from_url", fake_redis_from_url(broker)):
        with patch.object(Request, "is_disconnected", disconnect_after(1)):
            with client.stream(
                "GET", f"/api/observe/v1/sessions/{run_id}/stream", headers=_headers()
            ) as resp:
                body = resp.read()

    frames = _frames(body)
    ids = [fid for _e, fid, _d in frames if fid is not None]
    assert ids == ["1"]


# --- mid-stream auth re-check still runs on the new (redis-based) loop -----


def test_mid_stream_auth_revoke_still_ends_stream_with_forbidden(tmp_path, monkeypatch) -> None:
    run_id, session_id = "run-revoke", "sess-revoke"
    _seed_session(tmp_path, run_id, session_id)
    _seed_event(tmp_path, run_id=run_id, session_id=session_id, summary="one")

    app = _app(tmp_path, monkeypatch, OBSERVE_SHARED_TOKEN="rotate-v1")

    def _rotate_token():
        app.state.settings.observe_shared_token = "rotate-v2"

    broker = FakeRedisBroker()
    broker.next_first_poll_hook = _rotate_token

    client = TestClient(app)
    with patch("redis.Redis.from_url", fake_redis_from_url(broker)):
        with patch.object(Request, "is_disconnected", disconnect_after(3)):
            with client.stream(
                "GET",
                f"/api/observe/v1/sessions/{run_id}/stream",
                headers={"Authorization": "Bearer rotate-v1"},
            ) as resp:
                assert resp.status_code == 200
                body = resp.read()

    frames = _frames(body)
    events = [e for e, _fid, _d in frames]
    assert "error" in events
    # No frames with a durable id after the forbidden error.
    error_idx = events.index("error")
    assert all(fid is None for _e, fid, _d in frames[error_idx:])
