"""Persist recursive_context_result.v1 artifacts."""

from __future__ import annotations

import json
import os
from pathlib import Path

from agent_control.memory.preflight_artifacts import (
    ArtifactConflictError,
    digest_payload,
    session_artifact_dir,
)
from agent_shared.models.memory_preflight import SessionArtifactRef
from agent_shared.models.recursive_context import SCHEMA_VERSION, RecursiveContextResult


def recursive_context_path(state_root: Path, project: str, session_id: str) -> Path:
    return session_artifact_dir(state_root, project, session_id) / "recursive_context_result.json"


def persist_recursive_context_artifact(
    state_root: Path,
    result: RecursiveContextResult,
) -> tuple[RecursiveContextResult, SessionArtifactRef, bool]:
    path = recursive_context_path(state_root, result.repo, result.session_id)
    body = result.model_dump(mode="json")
    body["artifact_digest"] = ""
    digest = digest_payload(body)
    stamped = result.model_copy(update={"artifact_digest": digest})
    raw = json.dumps(stamped.model_dump(mode="json"), indent=2, ensure_ascii=False).encode("utf-8")

    if path.is_file():
        existing_raw = path.read_bytes()
        try:
            existing = RecursiveContextResult.model_validate(
                json.loads(existing_raw.decode("utf-8"))
            )
        except (json.JSONDecodeError, ValueError) as exc:
            raise ArtifactConflictError(
                f"corrupt recursive_context_result at {path}: {exc}"
            ) from exc
        if existing.artifact_digest == digest or digest_payload(
            {**existing.model_dump(mode="json"), "artifact_digest": ""}
        ) == digest:
            ref = SessionArtifactRef(
                artifact_type="recursive_context_result",
                relative_path=_rel(state_root, path),
                digest=existing.artifact_digest or digest,
                byte_size=len(existing_raw),
                schema_name=SCHEMA_VERSION,
                created_at=existing.created_at,
            )
            return existing, ref, False
        raise ArtifactConflictError(
            f"recursive_context_result digest conflict for session {result.session_id}"
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(raw)
    os.replace(tmp, path)
    ref = SessionArtifactRef(
        artifact_type="recursive_context_result",
        relative_path=_rel(state_root, path),
        digest=digest,
        byte_size=len(raw),
        schema_name=SCHEMA_VERSION,
        created_at=stamped.created_at,
    )
    return stamped, ref, True


def load_recursive_context_artifact(
    state_root: Path, project: str, session_id: str
) -> RecursiveContextResult | None:
    path = recursive_context_path(state_root, project, session_id)
    if not path.is_file():
        return None
    return RecursiveContextResult.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _rel(state_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(state_root.resolve()).as_posix()
    except ValueError:
        return str(path)
