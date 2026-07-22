"""Agent Observatory HTTP routes (V6 T03; V9 T05 OAuth shell + versioned API)."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse

from agent_control.config import Settings, get_settings
from agent_control.observe import artifacts as observe_artifacts
from agent_control.observe import decisions as observe_decisions
from agent_control.observe.auth import (
    ObserveAuthRedirect,
    authorize_repo_read,
    require_observe_identity,
    require_observe_repo_read,
)
from agent_control.observe.notify import is_circuit_open, notify_channel, record_publish_failure
from agent_control.observe.projection import build_observation_projection
from agent_control.observe.store import ObserveStore
from agent_control.observe.ui import (
    current_state_view,
    live_log_view,
    templates,
    timeline_page_view,
)
from agent_shared.repo_identity import normalize_repo_full_name
from agent_control.session.storage import load_session_by_run, sessions_dir

logger = logging.getLogger(__name__)

observe_ui = APIRouter(tags=["observe-ui"])
observe_api = APIRouter(prefix="/api/observe", tags=["observe-api-legacy"])
observe_api_v1 = APIRouter(prefix="/api/observe/v1", tags=["observe-api"])


def _settings(request: Request) -> Settings:
    return getattr(request.app.state, "settings", None) or get_settings()


def _repo_sessions(state_root: Path, project: str, *, limit: int = 50) -> list[dict[str, Any]]:
    sdir = sessions_dir(state_root, project)
    if not sdir.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(sdir.glob("sess-*.json"), reverse=True)[:limit]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rows.append(
            {
                "session_id": data.get("session_id"),
                "run_id": (data.get("run_ids") or [None])[0],
                "trace_id": data.get("trace_id"),
                "command_kind": data.get("command_kind"),
                "status": data.get("status"),
                "invoked_by": data.get("invoked_by"),
                "updated_at": data.get("updated_at"),
            }
        )
    return rows


def _resolve_project_for_run(state_root: Path, run_id: str) -> str | None:
    projects_root = state_root / "projects"
    if not projects_root.exists():
        return None
    for owner_dir in projects_root.iterdir():
        if not owner_dir.is_dir():
            continue
        for repo_dir in owner_dir.iterdir():
            if not repo_dir.is_dir():
                continue
            idx = repo_dir / "sessions" / "by_run_id" / f"{run_id}.json"
            if idx.exists():
                return f"{owner_dir.name}/{repo_dir.name}"
    return None


def _resolve_canonical_project(settings: Settings, run_id: str, hint: str | None) -> str | None:
    """Derive the repo for *run_id* from server-side records, never from client input alone.

    A client-supplied ``project`` query parameter is accepted only as a
    normalization hint; the value actually used for both the authorization
    check and the data fetch is always the project this ``run_id`` resolves
    to under ``agent_state_root`` (session index) or ``observe.sqlite`` (V9
    T02 projection). This closes a confused-deputy gap where a caller with
    read access to repo A could otherwise supply ``project=A`` while reading
    a ``run_id`` that actually belongs to repo B.
    """
    normalized_hint = normalize_repo_full_name(hint) if hint else None

    resolved = _resolve_project_for_run(settings.agent_state_root, run_id)
    if resolved:
        if normalized_hint and normalized_hint != resolved:
            logger.warning(
                "observe_project_hint_mismatch run_id=%s hint=%s resolved=%s",
                run_id,
                normalized_hint,
                resolved,
            )
        return resolved

    # Fall back to the observe.sqlite projection: the run may have been
    # pruned from the live session index but still have projected rows.
    try:
        store = ObserveStore(settings.observe_db_path)
        return store.get_project_for_run(run_id)
    except Exception:
        logger.exception("observe_project_fallback_failed run_id=%s", run_id)
        return None


@observe_ui.get("/observe/repos/{owner}/{repo}")
def observe_repo_list(
    owner: str,
    repo: str,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_gitea_token: Annotated[str | None, Header(alias="X-Gitea-Token")] = None,
) -> dict[str, Any]:
    settings = _settings(request)
    project = normalize_repo_full_name(f"{owner}/{repo}") or f"{owner}/{repo}"
    require_observe_repo_read(
        project,
        request=request,
        authorization=authorization,
        x_gitea_token=x_gitea_token,
        settings=settings,
    )
    return {
        "project": project,
        "sessions": _repo_sessions(settings.agent_state_root, project),
    }


@observe_ui.get("/observe/sessions/{run_id}")
def observe_session_page(
    run_id: str,
    request: Request,
    project: str | None = Query(default=None, description="deprecated hint; canonical repo is derived from run_id"),
    after_sequence: int = Query(0, alias="after_sequence", description="decision timeline pagination cursor"),
    authorization: Annotated[str | None, Header()] = None,
    x_gitea_token: Annotated[str | None, Header(alias="X-Gitea-Token")] = None,
) -> HTMLResponse:
    """Five-panel Observatory session detail page (V9 T04; T07 decisions + artifacts).

    Panels: 1) current state from ``session_observation`` (H6, =
    ``AgentSession``); 2) decision timeline paginated over ``observe.sqlite``
    (safe-display payloads only, H1); 3) structured ``observe_decision.v1``
    decisions (T07, :mod:`agent_control.observe.decisions`), falling back to
    a placeholder pointing at panel 2 when none have been recorded yet;
    4) live logs via the protected SSE stream (T03), cookie-auth friendly
    for ``EventSource``, with an HTMX poll fallback that renders identically
    with JavaScript disabled; 5) artifacts with real dispositions (T07,
    :mod:`agent_control.observe.artifacts`, H5) -- ``metadata_only`` always
    listed, plus a redacted-view/redacted-download link only when every
    trust gate (path/symlink/size/MIME/hash) passes for that artifact right
    now. Every panel is server-rendered on this same request -- panel 2
    (the "basic timeline") needs no JavaScript at all, only plain
    ``<a href>`` pagination links.
    """
    settings = _settings(request)
    # Identity (401/redirect) must be checked before resource existence, so
    # an unauthenticated caller never learns whether a run_id exists.
    identity = require_observe_identity(
        request=request,
        authorization=authorization,
        x_gitea_token=x_gitea_token,
        settings=settings,
    )
    canonical_project = _resolve_canonical_project(settings, run_id, project)
    if not canonical_project:
        raise HTTPException(status_code=404, detail="session not found")
    authorize_repo_read(identity, canonical_project, settings)

    session = load_session_by_run(settings.agent_state_root, canonical_project, run_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")

    store = ObserveStore(settings.observe_db_path)
    context = {
        "run_id": run_id,
        "run_id_urlsafe": quote(run_id, safe=""),
        "current_state": current_state_view(session, store, state_root=settings.agent_state_root),
        "timeline": timeline_page_view(store, run_id, after_sequence=after_sequence),
        "decisions": observe_decisions.decisions_panel_view(
            settings.agent_state_root, project=canonical_project, run_id=run_id
        ),
        "live_log": live_log_view(store, run_id),
        "artifacts": {"artifacts": observe_artifacts.artifact_disposition_rows(session, settings.agent_state_root)},
    }
    return templates.TemplateResponse(request, "session_detail.html", context)


@observe_ui.get("/observe/sessions/{run_id}/artifacts/{artifact_id}/view")
def observe_artifact_redacted_view(
    run_id: str,
    artifact_id: str,
    request: Request,
    project: str | None = Query(default=None, description="deprecated hint; canonical repo is derived from run_id"),
    authorization: Annotated[str | None, Header()] = None,
    x_gitea_token: Annotated[str | None, Header(alias="X-Gitea-Token")] = None,
) -> HTMLResponse:
    """``redacted_text_view`` artifact disposition (V9 T07, H5).

    ``artifact_id`` is opaque (:func:`agent_control.observe.artifacts.artifact_id_for`)
    -- this route never accepts, and the artifacts module never derives, a
    filesystem path from the request. Runs the same auth matrix as every
    other run_id-keyed route, then re-runs every trust gate (path/symlink/
    size/MIME/hash) fresh on this request; any gate failure or unknown
    ``artifact_id`` renders identically as a 404, never distinguishing the
    two to the caller.
    """
    settings = _settings(request)
    identity = require_observe_identity(
        request=request,
        authorization=authorization,
        x_gitea_token=x_gitea_token,
        settings=settings,
    )
    canonical_project = _resolve_canonical_project(settings, run_id, project)
    if not canonical_project:
        raise HTTPException(status_code=404, detail="session not found")
    authorize_repo_read(identity, canonical_project, settings)

    session = load_session_by_run(settings.agent_state_root, canonical_project, run_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")

    view = observe_artifacts.get_redacted_text_view(session, settings.agent_state_root, artifact_id)
    if view is None:
        raise HTTPException(status_code=404, detail="artifact not available")

    context = {
        "run_id": run_id,
        "run_id_urlsafe": quote(run_id, safe=""),
        "artifact_kind": view.kind,
        "artifact_type": view.artifact_type,
        "artifact_text": view.text,
    }
    return templates.TemplateResponse(request, "artifact_redacted_view.html", context)


@observe_ui.get("/observe/sessions/{run_id}/artifacts/{artifact_id}/download")
def observe_artifact_download(
    run_id: str,
    artifact_id: str,
    request: Request,
    project: str | None = Query(default=None, description="deprecated hint; canonical repo is derived from run_id"),
    authorization: Annotated[str | None, Header()] = None,
    x_gitea_token: Annotated[str | None, Header(alias="X-Gitea-Token")] = None,
) -> Response:
    """``downloadable_redacted_copy`` artifact disposition (V9 T07, H5).

    Always serves a freshly re-serialized, redacted JSON document -- never
    the original artifact bytes (default no raw download). Same auth
    matrix and opaque-``artifact_id`` contract as the redacted text view
    above.
    """
    settings = _settings(request)
    identity = require_observe_identity(
        request=request,
        authorization=authorization,
        x_gitea_token=x_gitea_token,
        settings=settings,
    )
    canonical_project = _resolve_canonical_project(settings, run_id, project)
    if not canonical_project:
        raise HTTPException(status_code=404, detail="session not found")
    authorize_repo_read(identity, canonical_project, settings)

    session = load_session_by_run(settings.agent_state_root, canonical_project, run_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")

    download = observe_artifacts.get_redacted_download(session, settings.agent_state_root, artifact_id)
    if download is None:
        raise HTTPException(status_code=404, detail="artifact not available")

    return Response(
        content=download.content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{download.filename}"'},
    )


@observe_ui.get("/observe/sessions/{run_id}/live-fragment")
def observe_session_live_fragment(
    run_id: str,
    request: Request,
    project: str | None = Query(default=None, description="deprecated hint; canonical repo is derived from run_id"),
    authorization: Annotated[str | None, Header()] = None,
    x_gitea_token: Annotated[str | None, Header(alias="X-Gitea-Token")] = None,
) -> HTMLResponse:
    """Panel 4 HTMX-poll fallback fragment (V9 T04).

    Returns the same safe-display "latest events" snapshot
    (:func:`agent_control.observe.ui.live_log_view`) the full page embeds on
    initial load, re-fetched on an ``hx-trigger="every 5s"`` interval. Never
    a substitute for the SSE stream's authorization -- this route runs the
    exact same 401/redirect/403/503 checks as every other run_id-keyed
    route, re-checked on every poll.
    """
    settings = _settings(request)
    identity = require_observe_identity(
        request=request,
        authorization=authorization,
        x_gitea_token=x_gitea_token,
        settings=settings,
    )
    canonical_project = _resolve_canonical_project(settings, run_id, project)
    if not canonical_project:
        raise HTTPException(status_code=404, detail="session not found")
    authorize_repo_read(identity, canonical_project, settings)

    store = ObserveStore(settings.observe_db_path)
    context = {"live_log": live_log_view(store, run_id)}
    return templates.TemplateResponse(request, "_live_log_rows.html", context)


def observe_session_events(
    run_id: str,
    request: Request,
    project: str | None = Query(default=None, description="deprecated hint; canonical repo is derived from run_id"),
    authorization: Annotated[str | None, Header()] = None,
    x_gitea_token: Annotated[str | None, Header(alias="X-Gitea-Token")] = None,
) -> dict[str, Any]:
    settings = _settings(request)
    identity = require_observe_identity(
        request=request,
        authorization=authorization,
        x_gitea_token=x_gitea_token,
        settings=settings,
    )
    canonical_project = _resolve_canonical_project(settings, run_id, project)
    if not canonical_project:
        raise HTTPException(status_code=404, detail="session not found")
    authorize_repo_read(identity, canonical_project, settings)
    doc = build_observation_projection(settings.agent_state_root, project=canonical_project, run_id=run_id)
    return doc.model_dump(mode="json")


def observe_session_artifacts(
    run_id: str,
    request: Request,
    project: str | None = Query(default=None, description="deprecated hint; canonical repo is derived from run_id"),
    authorization: Annotated[str | None, Header()] = None,
    x_gitea_token: Annotated[str | None, Header(alias="X-Gitea-Token")] = None,
) -> dict[str, Any]:
    settings = _settings(request)
    identity = require_observe_identity(
        request=request,
        authorization=authorization,
        x_gitea_token=x_gitea_token,
        settings=settings,
    )
    canonical_project = _resolve_canonical_project(settings, run_id, project)
    if not canonical_project:
        raise HTTPException(status_code=404, detail="session not found")
    authorize_repo_read(identity, canonical_project, settings)
    session = load_session_by_run(settings.agent_state_root, canonical_project, run_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    refs: dict[str, Any] = {}
    for name in ("memory_preflight", "context_packet", "recursive_context", "verification"):
        ref = getattr(session, name, None)
        if ref is not None:
            refs[name] = ref.model_dump(mode="json")
    return {"session_id": session.session_id, "run_id": run_id, "artifacts": refs}


def _format_sse_row(row: dict[str, Any]) -> str:
    """One ``observe_events`` row -> one SSE frame.

    H4 cursor contract: the SSE ``id:`` (and the embedded event's
    ``sequence`` field) is always the durable, per-run
    ``projection_sequence`` from observe.sqlite (H3) -- never a timestamp,
    and never whatever stale ``sequence`` value happened to be baked into
    ``observe_event_json`` when it was first written (T01/T02 write that
    JSON from the raw ledger event, which carries no meaningful per-run
    sequence of its own).
    """
    seq = int(row["projection_sequence"])
    try:
        event_dict = json.loads(row["observe_event_json"])
    except (TypeError, ValueError):
        event_dict = {}
    if not isinstance(event_dict, dict):
        event_dict = {}
    event_dict["sequence"] = seq
    return f"id: {seq}\ndata: {json.dumps(event_dict)}\n\n"


def _drain_new_rows(store: ObserveStore, run_id: str, after: int):
    """Yield every ``observe_events`` row for *run_id* with
    ``projection_sequence > after``, paging until exhausted (H4 step 3/5:
    the authoritative source is always this store, however many pages that
    takes -- never a single trusted row from a notify payload alone).
    """
    cursor = after
    while True:
        rows = store.list_events_for_run(run_id, after_sequence=cursor, limit=500)
        if not rows:
            return
        for row in rows:
            cursor = int(row["projection_sequence"])
            yield row
        if len(rows) < 500:
            return


async def observe_session_stream(
    run_id: str,
    request: Request,
    project: str | None = Query(default=None, description="deprecated hint; canonical repo is derived from run_id"),
    after_sequence: int = Query(0, alias="after_sequence"),
    authorization: Annotated[str | None, Header()] = None,
    x_gitea_token: Annotated[str | None, Header(alias="X-Gitea-Token")] = None,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    """Protected SSE stream over the observe.sqlite projection (V9 T03).

    Implements the H4 protected-SSE contract in order:

    1. Authorize before the stream (below, synchronous, before
       ``StreamingResponse`` is ever constructed -- an unauthorized caller
       gets a plain 401/403/503, never a 200 stream with an error event).
    2. Subscribe to this run's Redis notify channel FIRST, before reading
       any SQLite history, so an event projected in the gap between
       "subscribe" and "read history" can never be missed (it lands in the
       history read below and/or arrives again as a live notify --
       harmless either way, since both paths dedupe by projection_sequence).
    3. Emit every observe.sqlite row with ``projection_sequence > after``
       (``after`` = ``Last-Event-ID`` / ``?after_sequence=``, whichever is
       higher).
    4. Drain Redis notifications for as long as the client stays connected.
    5. For each notification: never trust its payload as display data --
       re-read observe.sqlite for anything newer than the last sequence
       already sent, and dedupe by projection_sequence.

    Redis outage degrades live tailing only: if the initial subscribe
    fails, step 3's history is still complete and correct (observe.sqlite
    is the system of record for this endpoint), the stream says so via an
    ``event: degraded`` frame and ends; the client's ``EventSource`` will
    keep retrying with ``Last-Event-ID`` and gets a fully caught-up history
    on every retry even while Redis stays down.
    """
    settings = _settings(request)
    # H4 step 1 -- identity (401) before resource existence (404), same as
    # the other run_id-keyed routes.
    identity = require_observe_identity(
        request=request,
        authorization=authorization,
        x_gitea_token=x_gitea_token,
        settings=settings,
    )
    canonical_project = _resolve_canonical_project(settings, run_id, project)
    if not canonical_project:
        raise HTTPException(status_code=404, detail="session not found")
    authorize_repo_read(identity, canonical_project, settings)

    # Cursor: Last-Event-ID (what the client's EventSource actually
    # consumed on a prior attempt) and ?after_sequence= (explicit alias for
    # non-browser callers) both name the same durable projection_sequence
    # cursor -- take the higher of the two when both are present.
    start_after = after_sequence
    if last_event_id:
        try:
            start_after = max(start_after, int(last_event_id))
        except ValueError:
            pass

    store = ObserveStore(settings.observe_db_path)
    redis_url = settings.redis_url

    async def event_generator():
        last = start_after

        # H4 step 2 -- subscribe FIRST, before any SQLite read. Skip the
        # attempt entirely (and its DNS/connect cost) if a very recent
        # publish or subscribe already proved this redis_url unreachable --
        # see agent_control.observe.notify's shared per-process breaker.
        pubsub = None
        redis_client = None
        degraded = is_circuit_open(redis_url)
        if not degraded:
            try:
                import redis as redis_lib

                redis_client = redis_lib.Redis.from_url(
                    redis_url, socket_connect_timeout=2.0, socket_timeout=2.5
                )
                pubsub = redis_client.pubsub()
                pubsub.subscribe(notify_channel(run_id))
            except Exception:
                logger.warning("observe_sse_redis_subscribe_failed run_id=%s", run_id, exc_info=True)
                record_publish_failure(redis_url)
                degraded = True

        # H4 step 3 -- durable SQLite history, projection_sequence > after.
        for row in _drain_new_rows(store, run_id, last):
            last = int(row["projection_sequence"])
            yield _format_sse_row(row)

        if degraded:
            # Redis outage: degrade live tailing only -- history above is
            # complete and authoritative regardless.
            yield (
                "event: degraded\n"
                'data: {"detail":"redis unavailable; live updates paused, history is complete"}\n\n'
            )
            yield "event: end\ndata: {}\n\n"
            if redis_client is not None:
                try:
                    redis_client.close()
                except Exception:
                    pass
            return

        try:
            # H4 step 4 -- drain Redis notifications while connected.
            # Bounded duration (like the prior polling loop) so a single
            # SSE connection can't run forever; the client's EventSource
            # reconnects transparently with Last-Event-ID.
            for _ in range(150):
                if await request.is_disconnected():
                    break
                # Re-check auth periodically (shared-token rotation /
                # permission revoke / OAuth session expiry mid-stream).
                try:
                    live_settings = _settings(request)
                    require_observe_repo_read(
                        canonical_project,
                        request=request,
                        authorization=authorization,
                        x_gitea_token=x_gitea_token,
                        settings=live_settings,
                    )
                except (HTTPException, ObserveAuthRedirect):
                    yield 'event: error\ndata: {"detail":"forbidden"}\n\n'
                    break

                try:
                    # Blocking redis call -- run off the event loop so an
                    # idle stream (no notify for up to 2s) never stalls
                    # other concurrent requests in this process.
                    message = await asyncio.to_thread(pubsub.get_message, timeout=2.0)
                except Exception:
                    logger.warning("observe_sse_redis_drain_failed run_id=%s", run_id, exc_info=True)
                    record_publish_failure(redis_url)
                    yield (
                        "event: degraded\n"
                        'data: {"detail":"redis unavailable; live updates paused"}\n\n'
                    )
                    break
                if message is None or message.get("type") != "message":
                    continue

                # H4 step 5 -- the notify payload names a run_id/sequence;
                # it is never itself trusted as display data. Re-read
                # observe.sqlite for anything newer than `last` and dedupe
                # by projection_sequence there, not from this payload.
                try:
                    notify = json.loads(message["data"])
                except (TypeError, ValueError):
                    notify = {}
                if not isinstance(notify, dict) or notify.get("run_id") != run_id:
                    continue

                for row in _drain_new_rows(store, run_id, last):
                    last = int(row["projection_sequence"])
                    yield _format_sse_row(row)
            yield "event: end\ndata: {}\n\n"
        finally:
            if pubsub is not None:
                try:
                    pubsub.close()
                except Exception:
                    pass
            if redis_client is not None:
                try:
                    redis_client.close()
                except Exception:
                    pass

    response = StreamingResponse(event_generator(), media_type="text/event-stream")
    # NPM (nginx/Nginx Proxy Manager) buffers proxied responses by default,
    # which silently defeats SSE live delivery (the client sees nothing
    # until the connection closes) even though this endpoint streams
    # correctly end to end. `X-Accel-Buffering: no` disables nginx's
    # response buffering for this response; NPM's own proxy host config
    # additionally needs "Block Common Exploits" left off / a custom
    # `proxy_buffering off;` location snippet for this path -- see
    # docs/slice-v9-t03-protected-sse-redis-notify.md for the exact steps
    # and why that could not be smoke-tested from this environment.
    response.headers["X-Accel-Buffering"] = "no"
    response.headers["Cache-Control"] = "no-cache"
    return response


# V9 T05: mount the same handlers on both the legacy unversioned prefix
# (kept so nothing already depending on it breaks) and the new versioned
# `/api/observe/v1` prefix (the ticket's "mount /api/observe/v1/* behind
# auth" requirement) -- one implementation, two routers, so there is no
# second code path to keep in sync.
for _router in (observe_api, observe_api_v1):
    _router.add_api_route("/sessions/{run_id}/events", observe_session_events, methods=["GET"])
    _router.add_api_route("/sessions/{run_id}/artifacts", observe_session_artifacts, methods=["GET"])
    _router.add_api_route("/sessions/{run_id}/stream", observe_session_stream, methods=["GET"])


def register_observe_routes(app) -> None:
    app.include_router(observe_ui)
    app.include_router(observe_api)
    app.include_router(observe_api_v1)

    from agent_control.observe.oauth import observe_oauth_router

    app.include_router(observe_oauth_router)

    # V9 T04: vendored, unauthenticated static assets (htmx.min.js) for the
    # five-panel UI -- not a display surface itself (no session/observation
    # data), so it is exempt from the observe auth gate the same way
    # /observe/oauth/* already is. Path is under /observe/static, which the
    # ENFORCE_PUBLIC_SURFACE_RESTRICTION allowlist already exempts wholesale
    # via its "/observe" prefix check (see webhook_server.py).
    from starlette.staticfiles import StaticFiles

    from agent_control.observe.ui import STATIC_DIR

    app.mount("/observe/static", StaticFiles(directory=str(STATIC_DIR)), name="observe-static")

    @app.exception_handler(ObserveAuthRedirect)
    async def _observe_auth_redirect_handler(_request: Request, exc: ObserveAuthRedirect):
        return RedirectResponse(url=exc.location, status_code=302)
