"""Atomic agent session store + run_id → session_id index."""

from __future__ import annotations

import json
import os
from pathlib import Path

from agent_control.project_identity import canonical_project, sanitize_path_segment
from agent_shared.models.agent_session import AgentSession
from agent_shared.repo_identity import split_repo_full_name


class SessionStoreError(RuntimeError):
    """Durable session store failure (fail closed — do not enqueue)."""


def sessions_dir(state_root: Path, project: str) -> Path:
    repo_full = canonical_project(project)
    owner, repo = split_repo_full_name(repo_full)
    return (
        state_root
        / "projects"
        / sanitize_path_segment(owner)
        / sanitize_path_segment(repo)
        / "sessions"
    )


def session_path(state_root: Path, project: str, session_id: str) -> Path:
    return sessions_dir(state_root, project) / f"{sanitize_path_segment(session_id)}.json"


def run_index_path(state_root: Path, project: str, run_id: str) -> Path:
    return (
        sessions_dir(state_root, project)
        / "by_run_id"
        / f"{sanitize_path_segment(run_id)}.json"
    )


def _atomic_write_json(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, path)


def save_session(state_root: Path, session: AgentSession) -> Path:
    path = session_path(state_root, session.project, session.session_id)
    _atomic_write_json(path, session.model_dump_json(indent=2))
    return path


def load_session(state_root: Path, project: str, session_id: str) -> AgentSession | None:
    path = session_path(state_root, project, session_id)
    if not path.is_file():
        return None
    try:
        return AgentSession.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValueError):
        return None


def save_run_index(
    state_root: Path,
    *,
    project: str,
    run_id: str,
    session_id: str,
) -> Path:
    """Persist run_id → session_id. Rejects binding a run to a second session."""
    path = run_index_path(state_root, project, run_id)
    if path.is_file():
        existing = json.loads(path.read_text(encoding="utf-8"))
        bound = existing.get("session_id")
        if bound and bound != session_id:
            raise SessionStoreError(
                f"run_id {run_id} already bound to session {bound}; "
                f"cannot rebind to {session_id}"
            )
        if bound == session_id:
            return path
    body = json.dumps(
        {"run_id": run_id, "session_id": session_id, "project": canonical_project(project)},
        indent=2,
    )
    _atomic_write_json(path, body)
    return path


def lookup_session_id_by_run(
    state_root: Path,
    project: str,
    run_id: str,
) -> str | None:
    path = run_index_path(state_root, project, run_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    sid = data.get("session_id")
    return sid if isinstance(sid, str) and sid else None


def load_session_by_run(
    state_root: Path,
    project: str,
    run_id: str,
) -> AgentSession | None:
    sid = lookup_session_id_by_run(state_root, project, run_id)
    if not sid:
        return None
    return load_session(state_root, project, sid)


def persist_session_with_run_index(state_root: Path, session: AgentSession) -> Path:
    """Atomic-ish: write session then index for each run_id (index is create-once)."""
    if not session.run_ids:
        raise SessionStoreError("session must include at least one run_id")
    path = save_session(state_root, session)
    for run_id in session.run_ids:
        save_run_index(
            state_root,
            project=session.project,
            run_id=run_id,
            session_id=session.session_id,
        )
    return path


def list_sessions(
    state_root: Path,
    project: str,
    *,
    command_kind: str | None = None,
) -> list[AgentSession]:
    root = sessions_dir(state_root, project)
    if not root.is_dir():
        return []
    items: list[AgentSession] = []
    for path in sorted(root.glob("*.json")):
        if path.name.endswith(".tmp") or path.parent.name == "by_run_id":
            continue
        if not path.name.startswith("sess-"):
            continue
        try:
            session = AgentSession.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, ValueError):
            continue
        if command_kind is None or session.command_kind == command_kind:
            items.append(session)
    return items
