"""Agent Observatory HTTP routes (V6 T03; V9 T05 OAuth shell + versioned API)."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse

from agent_control.config import Settings, get_settings
from agent_control.observe.auth import (
    ObserveAuthRedirect,
    authorize_repo_read,
    require_observe_identity,
    require_observe_repo_read,
)
from agent_control.observe.projection import build_observation_projection
from agent_control.observe.store import ObserveStore
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
    authorization: Annotated[str | None, Header()] = None,
    x_gitea_token: Annotated[str | None, Header(alias="X-Gitea-Token")] = None,
) -> HTMLResponse:
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
    doc = build_observation_projection(settings.agent_state_root, project=canonical_project, run_id=run_id)
    events_json = json.dumps(doc.events, indent=2)
    html = f"""<!DOCTYPE html>
<html><head><title>Observe {run_id}</title></head>
<body>
<h1>Agent Observatory</h1>
<p>Run: <code>{run_id}</code> | Session: <code>{doc.session_id or ''}</code> |
Trace: <code>{doc.trace_id or ''}</code> | Status: {doc.status or ''}</p>
<p><a href="/api/observe/v1/sessions/{run_id}/events">Events JSON</a></p>
<pre id="events">{events_json}</pre>
<script>
const es = new EventSource('/api/observe/v1/sessions/{run_id}/stream');
es.onmessage = (m) => {{ document.getElementById('events').textContent += '\\n' + m.data; }};
</script>
</body></html>"""
    return HTMLResponse(html)


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


async def observe_session_stream(
    run_id: str,
    request: Request,
    project: str | None = Query(default=None, description="deprecated hint; canonical repo is derived from run_id"),
    after_sequence: int = Query(0, alias="after_sequence"),
    authorization: Annotated[str | None, Header()] = None,
    x_gitea_token: Annotated[str | None, Header(alias="X-Gitea-Token")] = None,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    settings = _settings(request)
    # Identity (401) before resource existence (404), same as the other
    # run_id-keyed routes -- and, per H4 / V9 T05, all of this (identity,
    # existence, and the repo-read authorize call) happens BEFORE the
    # StreamingResponse (and its 200 status line) is ever constructed. An
    # unauthorized caller gets a plain 401/403/503 response, never a 200
    # stream that merely emits an error event. This is synchronous code
    # above, not inside, `event_generator`.
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
    start_after = after_sequence
    if last_event_id:
        try:
            start_after = max(start_after, int(last_event_id))
        except ValueError:
            pass

    async def event_generator():
        last = start_after
        for _ in range(30):
            if await request.is_disconnected():
                break
            # Re-check auth periodically (shared-token rotation / permission revoke).
            # Reload settings each tick so app.state.settings mutations and the
            # .observe_shared_token hot-reload file are observed mid-stream.
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
            live_settings = _settings(request)
            doc = build_observation_projection(
                live_settings.agent_state_root, project=canonical_project, run_id=run_id
            )
            for ev in doc.events:
                seq = int(ev.get("sequence") or 0)
                if seq > last:
                    last = seq
                    yield f"id: {seq}\ndata: {json.dumps(ev)}\n\n"
            await asyncio.sleep(2)
        yield "event: end\ndata: {}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


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

    @app.exception_handler(ObserveAuthRedirect)
    async def _observe_auth_redirect_handler(_request: Request, exc: ObserveAuthRedirect):
        return RedirectResponse(url=exc.location, status_code=302)
