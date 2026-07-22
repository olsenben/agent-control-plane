"""V9 T05 -- Gitea OAuth session shell + protected observe router.

Covers the ticket's auth response matrix end-to-end:

- unauth UI (Accept: text/html)  -> 302 redirect to /observe/oauth/login
- unauth API/SSE (no html accept) -> 401 JSON
- auth, no repo-read              -> 403
- Gitea permission check unreachable/5xx -> 503 (never 403)
- SSE authorizes before the stream is opened (no 200 + error-event fallback)
- OBSERVE_SHARED_TOKEN keeps working whether or not OAuth is configured
- OAuth login/callback/logout: fail-closed when unconfigured, state binding
  (CSRF), single-use state (anti-replay), fresh server-minted session id
  (anti session-fixation), Secure/HttpOnly/SameSite cookies
- /api/observe/v1/* versioned mount behind the same auth
- confused-deputy: repo is derived from the run_id's own session/observation
  record, not trusted from a client-supplied `project` query param
- ENFORCE_PUBLIC_SURFACE_RESTRICTION: oauth + observe stay reachable; /docs,
  /redoc, /openapi.json stay 404'd
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from agent_control.observe.auth import SESSION_COOKIE_NAME, STATE_COOKIE_NAME
from agent_control.observe.events import append_control_decision
from agent_control.observe.session_store import ObserveSessionStore
from agent_control.session.storage import persist_session_with_run_index
from agent_control.webhook_server import create_app
from agent_shared.models.agent_session import AgentSession, SessionStatus

PROJECT_A = "ai-sdlc-lab/demo-app-a"
PROJECT_B = "ai-sdlc-lab/demo-app-b"


def _seed_session(root: Path, project: str, run_id: str, session_id: str) -> None:
    session = AgentSession(
        session_id=session_id,
        project=project,
        repo=project.split("/", 1)[1],
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
        created_at="2026-07-21T00:00:00+00:00",
        updated_at="2026-07-21T00:00:00+00:00",
    )
    persist_session_with_run_index(root, session)
    append_control_decision(
        root,
        project=project,
        kind="other",
        summary="v9-t05-seed",
        session_id=session.session_id,
        run_id=run_id,
        trace_id=session.trace_id,
    )


def _app(tmp_path: Path, monkeypatch, **env):
    monkeypatch.setenv("AGENT_STATE_ROOT", str(tmp_path))
    monkeypatch.setenv("OBSERVE_REQUIRE_AUTH", "true")
    monkeypatch.setenv("GITEA_BASE_URL", "https://git.example.test")
    monkeypatch.delenv("OBSERVE_SHARED_TOKEN", raising=False)
    monkeypatch.delenv("OBSERVE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("OBSERVE_OAUTH_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("OBSERVE_OAUTH_REDIRECT_URI", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return create_app()


def _mock_repo_resp(has_pull: bool, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {"permissions": {"pull": has_pull}}
    return resp


# --- unauth response matrix -------------------------------------------------


def test_unauth_ui_redirects_to_login(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    client = TestClient(app)
    resp = client.get(
        "/observe/repos/ai-sdlc-lab/demo-app",
        headers={"Accept": "text/html"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    location = resp.headers["location"]
    assert location.startswith("/observe/oauth/login?next=")
    assert "demo-app" in location


def test_unauth_api_no_html_accept_is_401_json(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    client = TestClient(app)
    resp = client.get("/observe/repos/ai-sdlc-lab/demo-app")
    assert resp.status_code == 401
    assert resp.json()["detail"]


def test_unauth_sse_is_401_not_redirect(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    _seed_session(tmp_path, PROJECT_A, "run-sse-unauth", "sess-sse-unauth")
    client = TestClient(app)
    # EventSource sends Accept: text/event-stream, never text/html.
    resp = client.get(
        "/api/observe/v1/sessions/run-sse-unauth/stream",
        headers={"Accept": "text/event-stream"},
    )
    assert resp.status_code == 401
    assert resp.headers["content-type"].startswith("application/json")


def test_html_page_route_unauth_redirects(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    _seed_session(tmp_path, PROJECT_A, "run-page-unauth", "sess-page-unauth")
    client = TestClient(app)
    resp = client.get(
        "/observe/sessions/run-page-unauth",
        headers={"Accept": "text/html,application/xhtml+xml"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"].startswith("/observe/oauth/login?next=")


def test_auth_no_repo_read_is_403(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    client = TestClient(app)
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.get.return_value = _mock_repo_resp(has_pull=False)
    with patch("httpx.Client", return_value=mock_client):
        resp = client.get(
            "/observe/repos/ai-sdlc-lab/demo-app",
            headers={"Authorization": "Bearer some-user-token"},
        )
    assert resp.status_code == 403


def test_gitea_unavailable_is_503_not_403(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    client = TestClient(app)
    import httpx as httpx_mod

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.get.side_effect = httpx_mod.ConnectError("connection refused")
    with patch("httpx.Client", return_value=mock_client):
        resp = client.get(
            "/observe/repos/ai-sdlc-lab/demo-app",
            headers={"Authorization": "Bearer some-user-token"},
        )
    assert resp.status_code == 503
    assert resp.status_code != 403


def test_gitea_5xx_is_503_not_403(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    client = TestClient(app)
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.get.return_value = _mock_repo_resp(has_pull=False, status_code=502)
    with patch("httpx.Client", return_value=mock_client):
        resp = client.get(
            "/observe/repos/ai-sdlc-lab/demo-app",
            headers={"Authorization": "Bearer some-user-token"},
        )
    assert resp.status_code == 503


def test_shared_token_still_works_without_oauth_configured(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch, OBSERVE_SHARED_TOKEN="shared-secret-v9t05")
    client = TestClient(app)
    resp = client.get(
        "/observe/repos/ai-sdlc-lab/demo-app",
        headers={"Authorization": "Bearer shared-secret-v9t05"},
    )
    assert resp.status_code == 200


# --- SSE authorize-before-open ----------------------------------------------


def test_sse_unauthorized_never_returns_200(tmp_path, monkeypatch) -> None:
    """A denied SSE caller gets a bare status, never a 200 stream body."""
    app = _app(tmp_path, monkeypatch)
    _seed_session(tmp_path, PROJECT_A, "run-sse-403", "sess-sse-403")
    client = TestClient(app)
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.get.return_value = _mock_repo_resp(has_pull=False)
    with patch("httpx.Client", return_value=mock_client):
        with client.stream(
            "GET",
            "/api/observe/v1/sessions/run-sse-403/stream",
            headers={"Authorization": "Bearer no-read-token"},
        ) as resp:
            assert resp.status_code == 403
            body = resp.read()
    assert body == b"" or b"event:" not in body


# --- versioned mount ---------------------------------------------------------


def test_v1_and_legacy_events_routes_both_work(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch, OBSERVE_SHARED_TOKEN="shared-v9t05")
    _seed_session(tmp_path, PROJECT_A, "run-v1-parity", "sess-v1-parity")
    client = TestClient(app)
    headers = {"Authorization": "Bearer shared-v9t05"}
    legacy = client.get("/api/observe/sessions/run-v1-parity/events", headers=headers)
    v1 = client.get("/api/observe/v1/sessions/run-v1-parity/events", headers=headers)
    assert legacy.status_code == 200
    assert v1.status_code == 200
    assert legacy.json() == v1.json()


# --- confused-deputy: derive repo from session record, not client input -----


def test_repo_derived_from_run_id_not_client_supplied_project_hint(tmp_path, monkeypatch) -> None:
    """A caller with read on PROJECT_A cannot use `project=PROJECT_A` to read a
    run_id that actually belongs to PROJECT_B; canonical resolution must ignore
    the mismatched hint and authorize (then fetch) against the true owner.
    """
    app = _app(tmp_path, monkeypatch)
    _seed_session(tmp_path, PROJECT_B, "run-confused-deputy", "sess-confused-deputy")
    client = TestClient(app)

    def _get(url, headers=None, **kwargs):
        # Attacker has pull on PROJECT_A only, never on PROJECT_B.
        has_pull = PROJECT_A in url
        return _mock_repo_resp(has_pull=has_pull)

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.get.side_effect = _get
    with patch("httpx.Client", return_value=mock_client):
        resp = client.get(
            f"/api/observe/v1/sessions/run-confused-deputy/events?project={PROJECT_A}",
            headers={"Authorization": "Bearer attacker-token"},
        )
    # Must be checked (and denied) against PROJECT_B, the run's true owner --
    # not silently allowed through because the caller can read PROJECT_A.
    assert resp.status_code == 403


def test_project_hint_matching_owner_still_succeeds(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    _seed_session(tmp_path, PROJECT_B, "run-hint-match", "sess-hint-match")
    client = TestClient(app)
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.get.return_value = _mock_repo_resp(has_pull=True)
    with patch("httpx.Client", return_value=mock_client):
        resp = client.get(
            f"/api/observe/v1/sessions/run-hint-match/events?project={PROJECT_B}",
            headers={"Authorization": "Bearer real-owner-token"},
        )
    assert resp.status_code == 200
    assert resp.json()["project"] == PROJECT_B


def test_unknown_run_id_is_404(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch, OBSERVE_SHARED_TOKEN="shared-404")
    client = TestClient(app)
    resp = client.get(
        "/api/observe/v1/sessions/run-does-not-exist/events",
        headers={"Authorization": "Bearer shared-404"},
    )
    assert resp.status_code == 404


# --- ENFORCE_PUBLIC_SURFACE_RESTRICTION --------------------------------------


def test_docs_redoc_openapi_stay_restricted(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch, ENFORCE_PUBLIC_SURFACE_RESTRICTION="true")
    client = TestClient(app)
    for path in ("/docs", "/redoc", "/openapi.json"):
        resp = client.get(path)
        assert resp.status_code == 404, path


def test_oauth_and_observe_stay_reachable_under_restriction(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch, ENFORCE_PUBLIC_SURFACE_RESTRICTION="true")
    client = TestClient(app)
    # Unconfigured OAuth -> 503, not 404 -- the path itself is not blocked by
    # the public-surface restriction, only Observatory's own auth applies.
    resp = client.get("/observe/oauth/login")
    assert resp.status_code == 503
    resp = client.get("/api/observe/v1/sessions/whatever/events")
    assert resp.status_code == 401


# --- OAuth login/callback/logout --------------------------------------------


def test_login_fails_closed_when_unconfigured(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    client = TestClient(app)
    resp = client.get("/observe/oauth/login")
    assert resp.status_code == 503


def test_callback_fails_closed_when_unconfigured(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    client = TestClient(app)
    resp = client.get("/observe/oauth/callback?code=abc&state=def")
    assert resp.status_code == 503


def _oauth_env(**extra):
    base = {
        "OBSERVE_OAUTH_CLIENT_ID": "client-123",
        "OBSERVE_OAUTH_CLIENT_SECRET": "secret-456",
        "OBSERVE_OAUTH_REDIRECT_URI": "http://testserver/observe/oauth/callback",
    }
    base.update(extra)
    return base


def test_login_redirects_to_gitea_authorize_and_sets_state_cookie(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch, **_oauth_env())
    client = TestClient(app)
    resp = client.get("/observe/oauth/login?next=/observe/repos/ai-sdlc-lab/demo-app", follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers["location"]
    assert location.startswith("https://git.example.test/login/oauth/authorize?")
    assert "client_id=client-123" in location
    assert "state=" in location

    set_cookie = resp.headers.get("set-cookie", "")
    assert STATE_COOKIE_NAME in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "samesite=lax" in set_cookie.lower()


def test_login_rejects_open_redirect_next(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch, **_oauth_env())
    client = TestClient(app)
    resp = client.get(
        "/observe/oauth/login?next=https://evil.example.com/steal",
        follow_redirects=False,
    )
    assert resp.status_code == 302
    # State was created against the sanitized default, not the attacker URL --
    # verified end to end in the callback test below (next_path == /observe).
    store = app.state.observe_sessions
    # Extract state from the authorize-url redirect target.
    from urllib.parse import parse_qs, urlparse

    qs = parse_qs(urlparse(resp.headers["location"]).query)
    state = qs["state"][0]
    # consume_state returns the sanitized next path (peek without re-issuing).
    import sqlite3

    conn = sqlite3.connect(str(store.db_path))
    row = conn.execute(
        "SELECT next_path FROM observe_oauth_state WHERE state = ?", (state,)
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "/observe"


def _do_login(client: TestClient) -> tuple[str, str]:
    resp = client.get("/observe/oauth/login?next=/observe/repos/ai-sdlc-lab/demo-app", follow_redirects=False)
    from urllib.parse import parse_qs, urlparse

    qs = parse_qs(urlparse(resp.headers["location"]).query)
    state = qs["state"][0]
    state_cookie = resp.cookies.get(STATE_COOKIE_NAME)
    return state, state_cookie


def _mock_oauth_httpx(*, user_login="alice", user_id=42, access_token="gitea-access-tok"):
    def _post(url, json=None, headers=None, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"access_token": access_token, "token_type": "bearer"}
        return resp

    def _get(url, headers=None, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"login": user_login, "id": user_id}
        return resp

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.side_effect = _post
    mock_client.get.side_effect = _get
    return mock_client


def test_callback_success_sets_fresh_session_and_redirects(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch, **_oauth_env())
    client = TestClient(app)
    state, state_cookie = _do_login(client)

    mock_client = _mock_oauth_httpx()
    with patch("httpx.Client", return_value=mock_client):
        resp = client.get(
            f"/observe/oauth/callback?code=auth-code-1&state={state}",
            cookies={STATE_COOKIE_NAME: state_cookie},
            follow_redirects=False,
        )
    assert resp.status_code == 302
    assert resp.headers["location"] == "/observe/repos/ai-sdlc-lab/demo-app"

    set_cookie = resp.headers.get("set-cookie", "")
    assert SESSION_COOKIE_NAME in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "samesite=lax" in set_cookie.lower()

    session_id = resp.cookies.get(SESSION_COOKIE_NAME)
    assert session_id
    # Session id is a fresh server-minted token, never derived from the
    # client-controlled state/code values (anti session-fixation).
    assert session_id != state
    assert session_id != "auth-code-1"

    store: ObserveSessionStore = app.state.observe_sessions
    record = store.get_session(session_id)
    assert record is not None
    assert record["gitea_login"] == "alice"
    assert record["access_token"] == "gitea-access-tok"


def test_callback_session_cookie_grants_repo_access(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch, **_oauth_env())
    client = TestClient(app)
    state, state_cookie = _do_login(client)

    mock_client = _mock_oauth_httpx()
    with patch("httpx.Client", return_value=mock_client):
        callback_resp = client.get(
            f"/observe/oauth/callback?code=auth-code-2&state={state}",
            cookies={STATE_COOKIE_NAME: state_cookie},
            follow_redirects=False,
        )
    session_id = callback_resp.cookies.get(SESSION_COOKIE_NAME)

    repo_resp_mock = MagicMock()
    repo_resp_mock.status_code = 200
    repo_resp_mock.json.return_value = {"permissions": {"pull": True}}
    mock_client2 = MagicMock()
    mock_client2.__enter__.return_value = mock_client2
    mock_client2.get.return_value = repo_resp_mock
    with patch("httpx.Client", return_value=mock_client2):
        resp = client.get(
            "/observe/repos/ai-sdlc-lab/demo-app",
            cookies={SESSION_COOKIE_NAME: session_id},
        )
    assert resp.status_code == 200


def test_callback_missing_state_or_code_is_400(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch, **_oauth_env())
    client = TestClient(app)
    resp = client.get("/observe/oauth/callback?code=only-code")
    assert resp.status_code == 400


def test_callback_state_cookie_mismatch_is_400(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch, **_oauth_env())
    client = TestClient(app)
    state, _state_cookie = _do_login(client)
    resp = client.get(
        f"/observe/oauth/callback?code=abc&state={state}",
        cookies={STATE_COOKIE_NAME: "not-the-real-state-cookie"},
    )
    assert resp.status_code == 400


def test_callback_state_replay_is_rejected(tmp_path, monkeypatch) -> None:
    """A state value can only ever be consumed once -- defeats state/session
    fixation replay where an attacker captures a state+cookie pair and races
    the callback a second time."""
    app = _app(tmp_path, monkeypatch, **_oauth_env())
    client = TestClient(app)
    state, state_cookie = _do_login(client)

    mock_client = _mock_oauth_httpx()
    with patch("httpx.Client", return_value=mock_client):
        first = client.get(
            f"/observe/oauth/callback?code=auth-code-3&state={state}",
            cookies={STATE_COOKIE_NAME: state_cookie},
            follow_redirects=False,
        )
        second = client.get(
            f"/observe/oauth/callback?code=auth-code-3&state={state}",
            cookies={STATE_COOKIE_NAME: state_cookie},
            follow_redirects=False,
        )
    assert first.status_code == 302
    assert second.status_code == 400


def test_callback_gitea_unavailable_during_exchange_is_503(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch, **_oauth_env())
    client = TestClient(app)
    state, state_cookie = _do_login(client)

    import httpx as httpx_mod

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.side_effect = httpx_mod.ConnectError("refused")
    with patch("httpx.Client", return_value=mock_client):
        resp = client.get(
            f"/observe/oauth/callback?code=auth-code-4&state={state}",
            cookies={STATE_COOKIE_NAME: state_cookie},
        )
    assert resp.status_code == 503


def test_callback_gitea_rejects_code_is_401(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch, **_oauth_env())
    client = TestClient(app)
    state, state_cookie = _do_login(client)

    reject_resp = MagicMock()
    reject_resp.status_code = 400
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = reject_resp
    with patch("httpx.Client", return_value=mock_client):
        resp = client.get(
            f"/observe/oauth/callback?code=bad-code&state={state}",
            cookies={STATE_COOKIE_NAME: state_cookie},
        )
    assert resp.status_code == 401


def test_callback_gitea_error_param_is_400(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch, **_oauth_env())
    client = TestClient(app)
    resp = client.get("/observe/oauth/callback?error=access_denied&state=x")
    assert resp.status_code == 400


def test_logout_clears_session(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch, **_oauth_env())
    client = TestClient(app)
    state, state_cookie = _do_login(client)
    mock_client = _mock_oauth_httpx()
    with patch("httpx.Client", return_value=mock_client):
        callback_resp = client.get(
            f"/observe/oauth/callback?code=auth-code-5&state={state}",
            cookies={STATE_COOKIE_NAME: state_cookie},
            follow_redirects=False,
        )
    session_id = callback_resp.cookies.get(SESSION_COOKIE_NAME)

    logout_resp = client.get(
        "/observe/oauth/logout",
        cookies={SESSION_COOKIE_NAME: session_id},
        follow_redirects=False,
    )
    assert logout_resp.status_code == 302

    store: ObserveSessionStore = app.state.observe_sessions
    assert store.get_session(session_id) is None

    # Same cookie value no longer grants access (session-fixation defense
    # also covers "logged out cookie replay").
    resp = client.get(
        "/observe/repos/ai-sdlc-lab/demo-app",
        cookies={SESSION_COOKIE_NAME: session_id},
    )
    assert resp.status_code == 401


def test_forged_session_cookie_is_rejected(tmp_path, monkeypatch) -> None:
    """A client cannot pre-seed/guess a session id and have it accepted --
    only ids minted by create_session() (post-authentication) are valid."""
    app = _app(tmp_path, monkeypatch)
    client = TestClient(app)
    resp = client.get(
        "/observe/repos/ai-sdlc-lab/demo-app",
        cookies={SESSION_COOKIE_NAME: "attacker-picked-session-id"},
    )
    assert resp.status_code == 401


def test_two_logins_mint_different_session_ids(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch, **_oauth_env())
    client = TestClient(app)

    session_ids = []
    for i in range(2):
        state, state_cookie = _do_login(client)
        mock_client = _mock_oauth_httpx()
        with patch("httpx.Client", return_value=mock_client):
            resp = client.get(
                f"/observe/oauth/callback?code=auth-code-multi-{i}&state={state}",
                cookies={STATE_COOKIE_NAME: state_cookie},
                follow_redirects=False,
            )
        session_ids.append(resp.cookies.get(SESSION_COOKIE_NAME))

    assert session_ids[0] != session_ids[1]


def test_oauth_config_keys_default_empty(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    settings = app.state.settings
    assert settings.observe_oauth_client_id is None
    assert settings.observe_oauth_client_secret is None
    assert settings.observe_oauth_redirect_uri is None
