"""Gitea OAuth login/callback/logout for the Observatory (V9 T05).

Fail-closed by design: if ``OBSERVE_OAUTH_CLIENT_ID`` /
``OBSERVE_OAUTH_CLIENT_SECRET`` / ``OBSERVE_OAUTH_REDIRECT_URI`` are not all
configured, ``/observe/oauth/login`` and ``/observe/oauth/callback`` return
503 rather than crashing, falling back to an insecure path, or silently
no-op'ing. This agent never invents or mints client secrets -- see
``docs/slice-v9-t05-gitea-oauth-shell.md`` for the human checklist (same
secret-placement steps V8 T04 already documented; this ticket adds the
callback code that consumes them once a human supplies them).

Session-fixation defense: the session cookie value handed to the browser is
always a fresh :func:`secrets.token_urlsafe` id minted by
:meth:`ObserveSessionStore.create_session` *after* a successful Gitea code
exchange + user lookup -- never accepted from client input at any stage of
this flow. The OAuth ``state`` value is bound to both a short-lived,
single-use server-side record and an HttpOnly cookie; the callback only
proceeds when the query parameter, the cookie, and the server record all
agree, which defeats state replay / login-CSRF attempts that could otherwise
be used to force a victim into an attacker-controlled session.
"""

from __future__ import annotations

import hmac
import logging
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, Response

from agent_control.config import Settings, get_settings
from agent_control.observe.auth import (
    STATE_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    GiteaUnavailableError,
    resolve_session_store,
)

logger = logging.getLogger(__name__)

observe_oauth_router = APIRouter(prefix="/observe/oauth", tags=["observe-oauth"])

_DEFAULT_NEXT = "/observe"


class OAuthExchangeError(RuntimeError):
    """Gitea reached fine, but rejected the code/token (genuine auth failure)."""


def _settings(request: Request) -> Settings:
    return getattr(request.app.state, "settings", None) or get_settings()


def _oauth_configured(settings: Settings) -> bool:
    return bool(
        settings.observe_oauth_client_id
        and settings.observe_oauth_client_secret
        and settings.observe_oauth_redirect_uri
    )


def _sanitize_next(next_path: str | None) -> str:
    """Only ever redirect within our own app -- refuse open-redirect targets."""
    if not next_path:
        return _DEFAULT_NEXT
    if not next_path.startswith("/") or next_path.startswith("//"):
        return _DEFAULT_NEXT
    if "://" in next_path:
        return _DEFAULT_NEXT
    return next_path


def _authorize_url(settings: Settings, state: str) -> str:
    base = settings.gitea_base_url.rstrip("/")
    params = {
        "client_id": settings.observe_oauth_client_id,
        "redirect_uri": settings.observe_oauth_redirect_uri,
        "response_type": "code",
        "state": state,
    }
    if settings.observe_oauth_scope:
        params["scope"] = settings.observe_oauth_scope
    return f"{base}/login/oauth/authorize?{urlencode(params)}"


def _exchange_code(settings: Settings, code: str) -> dict:
    import httpx

    base = settings.gitea_base_url.rstrip("/")
    url = f"{base}/login/oauth/access_token"
    payload = {
        "client_id": settings.observe_oauth_client_id,
        "client_secret": settings.observe_oauth_client_secret,
        "redirect_uri": settings.observe_oauth_redirect_uri,
        "code": code,
        "grant_type": "authorization_code",
    }
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, json=payload, headers={"Accept": "application/json"})
    except httpx.HTTPError as exc:
        raise GiteaUnavailableError(str(exc)) from exc
    if resp.status_code >= 500:
        raise GiteaUnavailableError(f"gitea token endpoint status {resp.status_code}")
    if resp.status_code >= 400:
        raise OAuthExchangeError(f"gitea rejected code exchange: status {resp.status_code}")
    try:
        return resp.json()
    except ValueError as exc:
        raise GiteaUnavailableError("gitea token endpoint returned a non-JSON response") from exc


def _fetch_user(settings: Settings, access_token: str) -> dict:
    import httpx

    base = settings.gitea_base_url.rstrip("/")
    url = f"{base}/api/v1/user"
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, headers={"Authorization": f"token {access_token}"})
    except httpx.HTTPError as exc:
        raise GiteaUnavailableError(str(exc)) from exc
    if resp.status_code >= 500:
        raise GiteaUnavailableError(f"gitea user endpoint status {resp.status_code}")
    if resp.status_code >= 400:
        raise OAuthExchangeError(f"gitea rejected access token: status {resp.status_code}")
    try:
        return resp.json()
    except ValueError as exc:
        raise GiteaUnavailableError("gitea user endpoint returned a non-JSON response") from exc


@observe_oauth_router.get("/login")
def observe_oauth_login(
    request: Request,
    next: str | None = Query(default=None),  # noqa: A002 - matches OAuth convention
) -> Response:
    settings = _settings(request)
    if not _oauth_configured(settings):
        # Fail-closed: no client id/secret/redirect_uri in env means we do not
        # attempt a degraded/insecure flow -- see module docstring.
        raise HTTPException(status_code=503, detail="gitea oauth not configured")

    safe_next = _sanitize_next(next)
    store = resolve_session_store(request, settings)
    state = store.create_state(safe_next, ttl_seconds=settings.observe_oauth_state_ttl_seconds)

    response = RedirectResponse(url=_authorize_url(settings, state), status_code=302)
    response.set_cookie(
        STATE_COOKIE_NAME,
        state,
        httponly=True,
        secure=settings.observe_cookie_secure,
        samesite="lax",
        max_age=settings.observe_oauth_state_ttl_seconds,
        path="/observe/oauth",
    )
    return response


@observe_oauth_router.get("/callback")
def observe_oauth_callback(
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> Response:
    settings = _settings(request)
    if not _oauth_configured(settings):
        raise HTTPException(status_code=503, detail="gitea oauth not configured")

    if error:
        raise HTTPException(status_code=400, detail=f"gitea oauth error: {error}")
    if not state or not code:
        raise HTTPException(status_code=400, detail="missing oauth state or code")

    cookie_state = request.cookies.get(STATE_COOKIE_NAME)
    if not cookie_state or not hmac.compare_digest(state, cookie_state):
        raise HTTPException(status_code=400, detail="oauth state mismatch")

    store = resolve_session_store(request, settings)
    next_path = store.consume_state(state)
    if next_path is None:
        raise HTTPException(status_code=400, detail="oauth state expired or already used")

    try:
        token_data = _exchange_code(settings, code)
    except GiteaUnavailableError as exc:
        logger.warning("observe_oauth_gitea_unavailable stage=exchange error=%s", exc)
        raise HTTPException(status_code=503, detail="gitea oauth service unavailable") from exc
    except OAuthExchangeError as exc:
        logger.warning("observe_oauth_rejected stage=exchange error=%s", exc)
        raise HTTPException(status_code=401, detail="gitea rejected oauth code") from exc

    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=401, detail="gitea oauth response missing access_token")

    try:
        user = _fetch_user(settings, access_token)
    except GiteaUnavailableError as exc:
        logger.warning("observe_oauth_gitea_unavailable stage=user error=%s", exc)
        raise HTTPException(status_code=503, detail="gitea oauth service unavailable") from exc
    except OAuthExchangeError as exc:
        logger.warning("observe_oauth_rejected stage=user error=%s", exc)
        raise HTTPException(status_code=401, detail="gitea rejected oauth access token") from exc

    login = user.get("login")
    if not login:
        raise HTTPException(status_code=401, detail="gitea user profile missing login")

    # Fresh, server-minted identifier -- never derived from `state`, `code`, or
    # any other client-supplied value (session-fixation defense).
    session_id = store.create_session(
        gitea_login=login,
        gitea_user_id=user.get("id"),
        access_token=access_token,
        ttl_seconds=settings.observe_session_ttl_seconds,
    )

    response = RedirectResponse(url=next_path, status_code=302)
    response.delete_cookie(STATE_COOKIE_NAME, path="/observe/oauth")
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_id,
        httponly=True,
        secure=settings.observe_cookie_secure,
        samesite="lax",
        max_age=settings.observe_session_ttl_seconds,
        path="/",
    )
    return response


@observe_oauth_router.get("/logout")
@observe_oauth_router.post("/logout")
def observe_oauth_logout(request: Request) -> Response:
    settings = _settings(request)
    store = resolve_session_store(request, settings)
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    store.delete_session(session_id)

    response = RedirectResponse(url="/observe/oauth/login", status_code=302)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return response
