"""Agent Observatory HTTP routes (V6 T03)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from agent_control.config import Settings, get_settings
from agent_control.observe.projection import build_observation_projection
from agent_shared.repo_identity import normalize_repo_full_name
from agent_control.session.storage import load_session_by_run, sessions_dir

observe_ui = APIRouter(tags=["observe-ui"])
observe_api = APIRouter(prefix="/api/observe", tags=["observe-api"])


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


@observe_ui.get("/observe/repos/{owner}/{repo}")
def observe_repo_list(owner: str, repo: str, request: Request) -> dict[str, Any]:
    settings = _settings(request)
    project = normalize_repo_full_name(f"{owner}/{repo}") or f"{owner}/{repo}"
    return {
        "project": project,
        "sessions": _repo_sessions(settings.agent_state_root, project),
    }


@observe_ui.get("/observe/sessions/{run_id}")
def observe_session_page(run_id: str, request: Request) -> HTMLResponse:
    settings = _settings(request)
    project = _resolve_project_for_run(settings.agent_state_root, run_id)
    if not project:
        raise HTTPException(status_code=404, detail="session not found")
    doc = build_observation_projection(settings.agent_state_root, project=project, run_id=run_id)
    events_json = json.dumps(doc.events, indent=2)
    html = f"""<!DOCTYPE html>
<html><head><title>Observe {run_id}</title></head>
<body>
<h1>Agent Observatory</h1>
<p>Run: <code>{run_id}</code> | Session: <code>{doc.session_id or ''}</code> |
Trace: <code>{doc.trace_id or ''}</code> | Status: {doc.status or ''}</p>
<p><a href="/api/observe/sessions/{run_id}/events?project={project}">Events JSON</a></p>
<pre id="events">{events_json}</pre>
<script>
const es = new EventSource('/api/observe/sessions/{run_id}/stream?project={project}');
es.onmessage = (m) => {{ document.getElementById('events').textContent += '\\n' + m.data; }};
</script>
</body></html>"""
    return HTMLResponse(html)


@observe_api.get("/sessions/{run_id}/events")
def observe_session_events(
    run_id: str,
    request: Request,
    project: str = Query(..., description="owner/repo"),
) -> dict[str, Any]:
    settings = _settings(request)
    repo_full = normalize_repo_full_name(project) or project
    doc = build_observation_projection(settings.agent_state_root, project=repo_full, run_id=run_id)
    return doc.model_dump(mode="json")


@observe_api.get("/sessions/{run_id}/artifacts")
def observe_session_artifacts(
    run_id: str,
    request: Request,
    project: str = Query(...),
) -> dict[str, Any]:
    settings = _settings(request)
    repo_full = normalize_repo_full_name(project) or project
    session = load_session_by_run(settings.agent_state_root, repo_full, run_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    refs: dict[str, Any] = {}
    for name in ("memory_preflight", "context_packet", "recursive_context", "verification"):
        ref = getattr(session, name, None)
        if ref is not None:
            refs[name] = ref.model_dump(mode="json")
    return {"session_id": session.session_id, "run_id": run_id, "artifacts": refs}


@observe_api.get("/sessions/{run_id}/stream")
async def observe_session_stream(
    run_id: str,
    request: Request,
    project: str = Query(...),
    after_sequence: int = Query(0, alias="after_sequence"),
) -> StreamingResponse:
    settings = _settings(request)
    repo_full = normalize_repo_full_name(project) or project

    async def event_generator():
        last = after_sequence
        for _ in range(30):
            doc = build_observation_projection(settings.agent_state_root, project=repo_full, run_id=run_id)
            for ev in doc.events:
                seq = int(ev.get("sequence") or 0)
                if seq > last:
                    last = seq
                    yield f"id: {seq}\ndata: {json.dumps(ev)}\n\n"
            await asyncio.sleep(2)
        yield "event: end\ndata: {}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def register_observe_routes(app) -> None:
    app.include_router(observe_ui)
    app.include_router(observe_api)
