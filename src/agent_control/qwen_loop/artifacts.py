"""Persist qwen_loop_result.v1 artifacts."""

from __future__ import annotations

import json
import os
from pathlib import Path

from agent_control.memory.preflight_artifacts import (
    digest_payload,
    session_artifact_dir,
)
from agent_shared.models.memory_preflight import SessionArtifactRef
from agent_shared.models.qwen_loop import SCHEMA_VERSION, QwenLoopResult


def qwen_loop_path(state_root: Path, project: str, session_id: str) -> Path:
    return session_artifact_dir(state_root, project, session_id) / "qwen_loop_result.json"


def persist_qwen_loop_artifact(
    state_root: Path,
    result: QwenLoopResult,
) -> tuple[QwenLoopResult, SessionArtifactRef, bool]:
    """Overwrite-friendly persist — loop results advance attempt counters."""
    path = qwen_loop_path(state_root, result.repo, result.session_id)
    body = result.model_dump(mode="json")
    body["artifact_digest"] = ""
    digest = digest_payload(body)
    stamped = result.model_copy(update={"artifact_digest": digest})
    raw = json.dumps(stamped.model_dump(mode="json"), indent=2, ensure_ascii=False).encode("utf-8")

    created = not path.is_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(raw)
    os.replace(tmp, path)

    ref = SessionArtifactRef(
        artifact_type="qwen_loop_result",
        relative_path=_rel(state_root, path),
        digest=digest,
        byte_size=len(raw),
        schema_name=SCHEMA_VERSION,
        created_at=stamped.created_at or stamped.updated_at,
    )
    return stamped, ref, created


def load_qwen_loop_artifact(
    state_root: Path, project: str, session_id: str
) -> QwenLoopResult | None:
    path = qwen_loop_path(state_root, project, session_id)
    if not path.is_file():
        return None
    try:
        return QwenLoopResult.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValueError):
        return None


def _rel(state_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(state_root.resolve()).as_posix()
    except ValueError:
        return str(path)
