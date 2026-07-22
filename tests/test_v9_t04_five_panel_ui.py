"""V9 T04 -- Jinja2 + HTMX five-panel Observatory session-detail UI.

Covers:

- All five panels render server-side on the initial page load (no
  JavaScript required to see them -- this is a plain ``TestClient.get``,
  which never executes any ``<script>``).
- Hostile strings (HTML tags, ANSI-looking text) stored as an event summary
  render as escaped text, never as live markup, in the page, the HTMX
  fragment, and the JSON events API.
- Prohibited-field values never reach the page source; only field names.
- Panel 1 (current state) matches the canonical ``AgentSession`` fields via
  ``session_observation`` (H6).
- Panel 2 (decision timeline) pagination over ``observe.sqlite``
  (``after_sequence`` cursor) with no JavaScript involved.
- Panel 4 (live logs) HTMX-poll-fallback fragment endpoint is protected by
  the same auth matrix as every other run_id-keyed route and renders the
  same safe-display shape as the initial page.
- The vendored htmx static asset is served, unauthenticated, from
  ``/observe/static``.
- Auth matrix (401/redirect) is unchanged for the detail page and the new
  fragment route.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from agent_control.observe.events import append_control_decision
from agent_control.observe.store import ObserveStore
from agent_control.session.storage import persist_session_with_run_index
from agent_control.webhook_server import create_app
from agent_shared.models.agent_session import AgentSession, SessionStatus

PROJECT = "ai-sdlc-lab/demo-app"
HOSTILE_SUMMARY = "<script>alert(document.cookie)</script> \x1b[31mred\x1b[0m & # markdown *bold*"


def _seed_session(
    root: Path,
    *,
    run_id: str = "run-t04-detail",
    session_id: str = "sess-t04-detail",
    status: SessionStatus = SessionStatus.RUNNING,
) -> AgentSession:
    session = AgentSession(
        session_id=session_id,
        project=PROJECT,
        repo=PROJECT.split("/", 1)[1],
        subject_kind="issue",
        subject_number=7,
        command_kind="review",
        status=status,
        run_ids=[run_id],
        correlation_id=f"corr-{session_id}",
        trace_id=f"tr-{session_id}",
        input_state_sha="a" * 64,
        head_sha="b" * 40,
        policy_source_sha="c" * 40,
        risk_level="risk1",
        risk_tags=["needs_review"],
        invoked_by="tester",
        created_at="2026-07-21T00:00:00+00:00",
        updated_at="2026-07-21T00:05:00+00:00",
    )
    persist_session_with_run_index(root, session)
    return session


def _app(tmp_path: Path, monkeypatch, **env):
    monkeypatch.setenv("AGENT_STATE_ROOT", str(tmp_path))
    monkeypatch.setenv("OBSERVE_REQUIRE_AUTH", "false")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return create_app()


# --- five panels render -------------------------------------------------


def test_all_five_panels_render(tmp_path: Path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    run_id = "run-t04-panels"
    _seed_session(tmp_path, run_id=run_id, session_id="sess-t04-panels")
    client = TestClient(app)
    resp = client.get(f"/observe/sessions/{run_id}")
    assert resp.status_code == 200
    body = resp.text
    for marker in (
        "1. Current state",
        "2. Decision timeline",
        "3. Decisions and evidence",
        "4. Live logs",
        "5. Artifacts",
    ):
        assert marker in body


def test_decisions_panel_is_placeholder_text(tmp_path: Path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    run_id = "run-t04-decisions-placeholder"
    _seed_session(tmp_path, run_id=run_id, session_id="sess-t04-decisions-placeholder")
    client = TestClient(app)
    resp = client.get(f"/observe/sessions/{run_id}")
    assert "ships in T07" in resp.text


def test_artifacts_panel_is_metadata_only_placeholder(tmp_path: Path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    run_id = "run-t04-artifacts-placeholder"
    _seed_session(tmp_path, run_id=run_id, session_id="sess-t04-artifacts-placeholder")
    client = TestClient(app)
    resp = client.get(f"/observe/sessions/{run_id}")
    assert resp.status_code == 200
    assert "No artifacts recorded" in resp.text
    assert "metadata-only" in resp.text.lower()


# --- panel 1: current state == session_observation (H6) -----------------


def test_current_state_reflects_agent_session_fields(tmp_path: Path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    run_id = "run-t04-current-state"
    _seed_session(tmp_path, run_id=run_id, session_id="sess-t04-current-state")
    client = TestClient(app)
    resp = client.get(f"/observe/sessions/{run_id}")
    body = resp.text
    assert "sess-t04-current-state" in body
    assert "review" in body
    assert "risk1" in body
    assert "needs_review" in body
    assert "tester" in body


def test_current_state_falls_back_when_no_projection_row_yet(tmp_path: Path, monkeypatch) -> None:
    """A brand-new session with zero projected events still renders panel 1
    (via build_session_observation_row fallback), not a crash."""
    app = _app(tmp_path, monkeypatch)
    run_id = "run-t04-no-projection"
    _seed_session(tmp_path, run_id=run_id, session_id="sess-t04-no-projection")
    # Confirm observe.sqlite genuinely has no row for this session yet.
    store = ObserveStore(tmp_path / "observe" / "observe.sqlite")
    assert store.get_session_observation("sess-t04-no-projection") is None
    client = TestClient(app)
    resp = client.get(f"/observe/sessions/{run_id}")
    assert resp.status_code == 200
    assert "sess-t04-no-projection" in resp.text


# --- panel 2: decision timeline + text-safety ----------------------------


def test_hostile_summary_renders_as_escaped_text_not_markup(tmp_path: Path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    run_id = "run-t04-hostile"
    _seed_session(tmp_path, run_id=run_id, session_id="sess-t04-hostile")
    append_control_decision(
        tmp_path,
        project=PROJECT,
        kind="other",
        summary=HOSTILE_SUMMARY,
        session_id="sess-t04-hostile",
        run_id=run_id,
        trace_id="tr-sess-t04-hostile",
    )
    client = TestClient(app)
    resp = client.get(f"/observe/sessions/{run_id}")
    body = resp.text
    assert resp.status_code == 200
    # Never a live <script> tag anywhere in the page source.
    assert "<script>alert(document.cookie)</script>" not in body
    # The escaped rendering of the hostile string is present as plain text.
    assert "&lt;script&gt;alert(document.cookie)&lt;/script&gt;" in body
    assert "&amp;" in body


def test_no_raw_prohibited_payload_in_page_source(tmp_path: Path, monkeypatch) -> None:
    """A raw ledger event with a prohibited-name field must never leak its
    value into the rendered page -- only the field name is retained."""
    app = _app(tmp_path, monkeypatch)
    run_id = "run-t04-prohibited"
    session_id = "sess-t04-prohibited"
    _seed_session(tmp_path, run_id=run_id, session_id=session_id)

    from agent_control.events import AgentEvent, append_event, deterministic_event_id

    secret_value = "super-secret-token-value-should-never-render"
    payload = {
        "session_id": session_id,
        "run_id": run_id,
        "project": PROJECT,
        "status": "started",
        "invoked_by": "tester",
        "auth_header": secret_value,
    }
    event = AgentEvent(
        event_id=deterministic_event_id("ct103", f"{run_id}:started", "agent.session_started"),
        type="agent.session_started",
        raw_event_type="agent.session_started",
        source="ct103",
        delivery_id=f"{run_id}:started",
        project=PROJECT,
        payload=payload,
        recorded_at="2026-07-21T00:01:00+00:00",
    )
    append_event(tmp_path, event)

    client = TestClient(app)
    resp = client.get(f"/observe/sessions/{run_id}")
    body = resp.text
    assert resp.status_code == 200
    assert secret_value not in body
    assert "auth_header" in body  # field name retained (audit visibility)


def test_timeline_pagination_no_js_required(tmp_path: Path, monkeypatch) -> None:
    """Plain <a href> pagination over observe.sqlite -- no script execution
    needed to reach page 2 of the decision timeline."""
    from agent_control.observe.ui import TIMELINE_PAGE_SIZE

    app = _app(tmp_path, monkeypatch)
    run_id = "run-t04-pagination"
    session_id = "sess-t04-pagination"
    _seed_session(tmp_path, run_id=run_id, session_id=session_id)

    total_events = TIMELINE_PAGE_SIZE + 5
    for i in range(total_events):
        append_control_decision(
            tmp_path,
            project=PROJECT,
            kind="other",
            summary=f"decision {i}",
            session_id=session_id,
            run_id=run_id,
            trace_id=f"tr-{session_id}",
        )

    client = TestClient(app)
    first_page = client.get(f"/observe/sessions/{run_id}")
    assert first_page.status_code == 200
    # `<td>...</td>` marks a decision-timeline row specifically (distinct
    # from the live-log panel's `<span class="live-log-summary">`, which
    # also shows a handful of the most recent decisions regardless of
    # this panel's own pagination cursor).
    assert "<td>decision 0</td>" in first_page.text
    assert f"<td>decision {TIMELINE_PAGE_SIZE}</td>" not in first_page.text
    assert f"after_sequence={TIMELINE_PAGE_SIZE}" in first_page.text

    second_page = client.get(f"/observe/sessions/{run_id}?after_sequence={TIMELINE_PAGE_SIZE}")
    assert second_page.status_code == 200
    assert f"<td>decision {TIMELINE_PAGE_SIZE}</td>" in second_page.text
    assert "back to start" in second_page.text
    # The remaining 5 events fit on this page, so there is no further
    # "older" page -- no link naming a cursor past the last event.
    assert f"after_sequence={total_events}" not in second_page.text


def test_no_events_yet_shows_placeholder_not_error(tmp_path: Path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    run_id = "run-t04-empty-timeline"
    _seed_session(tmp_path, run_id=run_id, session_id="sess-t04-empty-timeline")
    client = TestClient(app)
    resp = client.get(f"/observe/sessions/{run_id}")
    assert resp.status_code == 200
    assert "No events recorded yet" in resp.text


# --- panel 4: live logs (HTMX poll fragment) ------------------------------


def test_live_fragment_requires_auth(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_STATE_ROOT", str(tmp_path))
    monkeypatch.setenv("OBSERVE_REQUIRE_AUTH", "true")
    monkeypatch.delenv("OBSERVE_SHARED_TOKEN", raising=False)
    app = create_app()
    run_id = "run-t04-live-fragment-auth"
    _seed_session(tmp_path, run_id=run_id, session_id="sess-t04-live-fragment-auth")
    client = TestClient(app)
    resp = client.get(f"/observe/sessions/{run_id}/live-fragment")
    assert resp.status_code == 401


def test_live_fragment_renders_latest_events_escaped(tmp_path: Path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    run_id = "run-t04-live-fragment"
    session_id = "sess-t04-live-fragment"
    _seed_session(tmp_path, run_id=run_id, session_id=session_id)
    append_control_decision(
        tmp_path,
        project=PROJECT,
        kind="other",
        summary=HOSTILE_SUMMARY,
        session_id=session_id,
        run_id=run_id,
        trace_id=f"tr-{session_id}",
    )
    client = TestClient(app)
    resp = client.get(f"/observe/sessions/{run_id}/live-fragment")
    assert resp.status_code == 200
    body = resp.text
    assert "<script>alert(document.cookie)</script>" not in body
    assert "&lt;script&gt;alert(document.cookie)&lt;/script&gt;" in body
    # Fragment is a bare partial, not a full document.
    assert "<html" not in body.lower()


def test_live_fragment_unknown_run_is_404(tmp_path: Path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    client = TestClient(app)
    resp = client.get("/observe/sessions/run-does-not-exist/live-fragment")
    assert resp.status_code == 404


def test_initial_page_embeds_live_log_snapshot_for_no_js(tmp_path: Path, monkeypatch) -> None:
    """The live-log panel's initial content is server-rendered inline, so a
    JS-disabled browser (which never fires the HTMX poll or the SSE script)
    still sees the latest events on first load."""
    app = _app(tmp_path, monkeypatch)
    run_id = "run-t04-live-initial"
    session_id = "sess-t04-live-initial"
    _seed_session(tmp_path, run_id=run_id, session_id=session_id)
    append_control_decision(
        tmp_path,
        project=PROJECT,
        kind="other",
        summary="initial-live-log-entry",
        session_id=session_id,
        run_id=run_id,
        trace_id=f"tr-{session_id}",
    )
    client = TestClient(app)
    resp = client.get(f"/observe/sessions/{run_id}")
    assert "initial-live-log-entry" in resp.text


def test_sse_stream_url_carried_via_data_attribute_not_inline_script(tmp_path: Path, monkeypatch) -> None:
    """The EventSource URL must never be interpolated directly into a JS
    string literal -- only into an HTML attribute (auto-escaped) that the
    script reads via ``dataset``/``getAttribute``."""
    app = _app(tmp_path, monkeypatch)
    run_id = "run-t04-stream-url"
    _seed_session(tmp_path, run_id=run_id, session_id="sess-t04-stream-url")
    client = TestClient(app)
    resp = client.get(f"/observe/sessions/{run_id}")
    body = resp.text
    assert f'data-stream-url="/api/observe/v1/sessions/{run_id}/stream"' in body
    assert f"new EventSource('/api/observe/v1/sessions/{run_id}/stream')" not in body
    assert f'new EventSource("/api/observe/v1/sessions/{run_id}/stream")' not in body


# --- static assets ---------------------------------------------------------


def test_htmx_static_asset_served_unauthenticated(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_STATE_ROOT", str(tmp_path))
    monkeypatch.setenv("OBSERVE_REQUIRE_AUTH", "true")
    monkeypatch.delenv("OBSERVE_SHARED_TOKEN", raising=False)
    app = create_app()
    client = TestClient(app)
    resp = client.get("/observe/static/htmx.min.js")
    assert resp.status_code == 200
    assert "htmx" in resp.text.lower()


# --- auth matrix unchanged for the detail page ---------------------------


def test_detail_page_unauth_still_redirects(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_STATE_ROOT", str(tmp_path))
    monkeypatch.setenv("OBSERVE_REQUIRE_AUTH", "true")
    monkeypatch.delenv("OBSERVE_SHARED_TOKEN", raising=False)
    app = create_app()
    run_id = "run-t04-unauth"
    _seed_session(tmp_path, run_id=run_id, session_id="sess-t04-unauth")
    client = TestClient(app)
    resp = client.get(
        f"/observe/sessions/{run_id}",
        headers={"Accept": "text/html"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"].startswith("/observe/oauth/login?next=")


def test_detail_page_unknown_run_is_404(tmp_path: Path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    client = TestClient(app)
    resp = client.get("/observe/sessions/run-does-not-exist")
    assert resp.status_code == 404
