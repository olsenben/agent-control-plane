"""Observatory repository-read authorization (V6 T03 QA hardening; V9 T05 OAuth shell).

Response matrix (V9 T05):

- No credential at all, request wants HTML (browser navigation) -> 302 redirect
  to ``/observe/oauth/login?next=<original path>``.
- No credential at all, request wants JSON/SSE -> 401.
- Credential present but lacks repo-read -> 403.
- Gitea itself is unreachable/erroring while checking repo-read -> 503, never
  403 -- a permission *check that could not be performed* must never be
  reported the same way as a permission that was checked and denied.
- Shared token (``OBSERVE_SHARED_TOKEN``) always still works when configured,
  regardless of OAuth configuration state (ops escape hatch, V8 T04).
- Session cookie (V9 T05 OAuth) resolves to a stored Gitea access token and is
  checked exactly like a bearer token from a header.
"""

from __future__ import annotations

import hmac
import logging
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import Header, HTTPException, Request

from agent_control.config import Settings, get_settings
from agent_control.observe.session_store import ObserveSessionStore

logger = logging.getLogger(__name__)

# Optional hot-reload file under agent_state_root for mid-SSE shared-token rotation
# without restarting the control-plane process (V8 T03).
OBSERVE_SHARED_TOKEN_FILENAME = ".observe_shared_token"

# Cookie names (V9 T05). Both are HttpOnly + SameSite=Lax (Lax survives the
# top-level GET navigation that lands back on our /observe/oauth/callback
# after Gitea redirects the browser) + Secure by default
# (Settings.observe_cookie_secure; disable only for plain-HTTP local dev).
SESSION_COOKIE_NAME = "observe_session"
STATE_COOKIE_NAME = "observe_oauth_state"


class GiteaUnavailableError(RuntimeError):
    """Gitea could not be reached / errored while checking a permission.

    Distinct from "checked and denied" -- callers must map this to 503, not
    403 (see module docstring / response matrix).
    """


class ObserveIdentity:
    """A resolved caller identity: a usable Gitea-checkable token, plus
    whether it matched the shared-secret escape hatch (which always grants
    read, skipping the per-repo Gitea call entirely)."""

    __slots__ = ("token", "is_shared")

    def __init__(self, token: str, *, is_shared: bool) -> None:
        self.token = token
        self.is_shared = is_shared


class ObserveAuthRedirect(Exception):
    """Raised instead of HTTPException when an unauthenticated *UI* request
    should be sent to the OAuth login flow rather than shown a bare 401.

    A FastAPI exception handler (registered in
    :func:`agent_control.observe.routes.register_observe_routes`) converts
    this into a 302 ``RedirectResponse``.
    """

    def __init__(self, location: str) -> None:
        self.location = location
        super().__init__(location)


def extract_bearer_token(
    authorization: str | None = None,
    x_gitea_token: str | None = None,
) -> str | None:
    if x_gitea_token and x_gitea_token.strip():
        return x_gitea_token.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return None


def resolve_observe_shared_token(settings: Settings) -> str:
    """Return the active Observatory shared bearer.

    Prefer ``<agent_state_root>/.observe_shared_token`` when present so operators
    (and V8 T03 proof) can rotate the shared token mid-stream without a restart.
    Falls back to ``OBSERVE_SHARED_TOKEN`` / settings.
    """
    root = getattr(settings, "agent_state_root", None)
    if root is not None:
        path = Path(root) / OBSERVE_SHARED_TOKEN_FILENAME
        try:
            if path.is_file():
                val = path.read_text(encoding="utf-8").strip()
                if val:
                    return val
        except OSError:
            logger.warning("observe_shared_token_file_unreadable path=%s", path)
    return (settings.observe_shared_token or "").strip()


def resolve_session_store(request: Request | None, settings: Settings) -> ObserveSessionStore:
    """Prefer the app-scoped store (one sqlite handle per app) when available."""
    if request is not None:
        existing = getattr(request.app.state, "observe_sessions", None)
        if existing is not None:
            return existing
    return ObserveSessionStore(settings.observe_sessions_db_path)


def _wants_html(request: Request | None) -> bool:
    """Content-negotiation, not route registration, decides redirect vs 401.

    A real browser navigating to an Observatory page sends
    ``Accept: text/html,...``; curl/httpx/EventSource smoke checks and API
    callers do not. This lets one auth dependency serve both the JSON-returning
    "UI-tagged" routes (e.g. ``/observe/repos/{owner}/{repo}``, historically
    tested to 401 without a browser Accept header) and true HTML page routes
    (``/observe/sessions/{run_id}``) correctly without per-route flags, and
    SSE requests (``Accept: text/event-stream``) always fall through to 401
    JSON as required.
    """
    if request is None:
        return False
    accept = request.headers.get("accept", "")
    return "text/html" in accept.lower()


def _login_redirect_location(request: Request | None) -> str:
    next_path = "/observe"
    if request is not None:
        next_path = request.url.path
        if request.url.query:
            next_path += f"?{request.url.query}"
    return f"/observe/oauth/login?next={quote(next_path, safe='')}"


def _token_has_repo_read(project: str, token: str, settings: Settings) -> bool:
    """Validate *token* can read *project* via Gitea API (as that user).

    Raises :class:`GiteaUnavailableError` when Gitea cannot be reached or
    errors at the transport/5xx level -- callers must map that to 503, never
    to the same 403 used for "reachable, and permission denied".
    """
    import httpx

    owner, repo = project.split("/", 1)
    base = settings.gitea_base_url.rstrip("/")
    url = f"{base}/api/v1/repos/{owner}/{repo}"
    headers = {"Authorization": f"token {token}"}
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        logger.warning("observe_auth_gitea_unavailable project=%s error=%s", project, exc)
        raise GiteaUnavailableError(str(exc)) from exc

    if resp.status_code >= 500:
        logger.warning(
            "observe_auth_gitea_5xx project=%s status=%s", project, resp.status_code
        )
        raise GiteaUnavailableError(f"gitea status {resp.status_code}")
    if resp.status_code == 404:
        return False
    if resp.status_code >= 400:
        logger.warning(
            "observe_auth_gitea_denied project=%s status=%s",
            project,
            resp.status_code,
        )
        return False
    try:
        data = resp.json()
    except ValueError as exc:
        logger.warning("observe_auth_gitea_bad_response project=%s error=%s", project, exc)
        raise GiteaUnavailableError("gitea returned a non-JSON response") from exc
    perms = data.get("permissions") or {}
    return bool(perms.get("pull") or perms.get("admin") or perms.get("push"))


def resolve_observe_identity(
    *,
    request: Request | None = None,
    authorization: str | None = None,
    x_gitea_token: str | None = None,
    settings: Settings,
    session_store: ObserveSessionStore | None = None,
) -> ObserveIdentity | None:
    """Find *some* credential (header bearer, shared token, or session cookie).

    Returns ``None`` when no credential is present at all -- callers decide
    401 vs redirect from that. Never makes the Gitea repo-read call itself
    (that requires knowing the target project, which some callers -- the
    run_id-keyed routes -- must not trust from client input alone; see
    :mod:`agent_control.observe.routes`).
    """
    header_token = extract_bearer_token(authorization, x_gitea_token)
    if not header_token and request is not None:
        header_token = extract_bearer_token(
            request.headers.get("authorization"),
            request.headers.get("x-gitea-token"),
        )

    if header_token:
        shared = resolve_observe_shared_token(settings)
        if shared and hmac.compare_digest(header_token, shared):
            return ObserveIdentity(header_token, is_shared=True)
        return ObserveIdentity(header_token, is_shared=False)

    if request is not None:
        session_id = request.cookies.get(SESSION_COOKIE_NAME)
        if session_id:
            store = session_store or resolve_session_store(request, settings)
            session = store.get_session(session_id)
            if session is not None:
                return ObserveIdentity(session["access_token"], is_shared=False)

    return None


def require_observe_identity(
    *,
    request: Request | None = None,
    authorization: str | None = None,
    x_gitea_token: str | None = None,
    settings: Settings | None = None,
    session_store: ObserveSessionStore | None = None,
) -> ObserveIdentity | None:
    """401/redirect gate that does *not* need to know the target project yet.

    Returns ``None`` when ``OBSERVE_REQUIRE_AUTH`` is disabled (auth
    intentionally bypassed) -- callers must treat ``None`` as "skip the
    per-repo authorize step too". Otherwise always returns a resolved
    :class:`ObserveIdentity` or raises (redirect for HTML callers, 401 JSON
    otherwise). This check must happen *before* any resource-existence
    lookup (e.g. resolving a run_id to a project) so an unauthenticated
    caller always gets 401/redirect regardless of whether the resource
    exists -- existence must never be observable without a credential.
    """
    settings = settings or get_settings()
    if not settings.observe_require_auth:
        return None

    identity = resolve_observe_identity(
        request=request,
        authorization=authorization,
        x_gitea_token=x_gitea_token,
        settings=settings,
        session_store=session_store,
    )
    if identity is None:
        if _wants_html(request):
            raise ObserveAuthRedirect(_login_redirect_location(request))
        raise HTTPException(status_code=401, detail="observatory authentication required")
    return identity


def authorize_repo_read(identity: ObserveIdentity | None, project: str, settings: Settings) -> None:
    """403/503 gate; requires the project to already be known.

    ``identity is None`` means auth was disabled by :func:`require_observe_identity`
    -- nothing further to check.
    """
    if identity is None:
        return
    if identity.is_shared:
        return
    try:
        has_read = _token_has_repo_read(project, identity.token, settings)
    except GiteaUnavailableError as exc:
        raise HTTPException(
            status_code=503, detail="gitea permission service unavailable"
        ) from exc
    if not has_read:
        raise HTTPException(status_code=403, detail="repository read access required")


def require_observe_repo_read(
    project: str,
    *,
    request: Request | None = None,
    authorization: str | None = None,
    x_gitea_token: str | None = None,
    settings: Settings | None = None,
    session_store: ObserveSessionStore | None = None,
) -> None:
    """Fail closed: unauthorized callers get redirect/401/403/503 (see matrix above).

    Convenience wrapper over :func:`require_observe_identity` +
    :func:`authorize_repo_read` for routes where *project* is already known
    from a trusted source (path params, e.g. ``/observe/repos/{owner}/{repo}``)
    before any auth check runs. Routes that derive their project from a
    ``run_id`` must call the two steps separately with the *resolved* project
    coming after the identity check -- see
    :mod:`agent_control.observe.routes`.
    """
    settings = settings or get_settings()
    identity = require_observe_identity(
        request=request,
        authorization=authorization,
        x_gitea_token=x_gitea_token,
        settings=settings,
        session_store=session_store,
    )
    authorize_repo_read(identity, project, settings)


def ObserveAuthDeps(
    authorization: Annotated[str | None, Header()] = None,
    x_gitea_token: Annotated[str | None, Header(alias="X-Gitea-Token")] = None,
) -> tuple[str | None, str | None]:
    return authorization, x_gitea_token
