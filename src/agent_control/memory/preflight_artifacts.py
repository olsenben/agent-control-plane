"""Atomic persistence for memory_preflight / context_packet artifacts (Slice 5.5a)."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from agent_control.project_identity import sanitize_path_segment
from agent_control.session.storage import sessions_dir
from agent_shared.models.memory_preflight import (
    ContextPacket,
    MemoryPreflight,
    SessionArtifactRef,
)


class ArtifactConflictError(RuntimeError):
    """Existing artifact digest differs from the candidate — fail closed."""


class ArtifactStoreError(RuntimeError):
    """Durable preflight/packet store failure."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def session_artifact_dir(state_root: Path, project: str, session_id: str) -> Path:
    return sessions_dir(state_root, project) / sanitize_path_segment(session_id)


def artifact_path(
    state_root: Path,
    project: str,
    session_id: str,
    artifact_type: Literal["memory_preflight", "context_packet"],
) -> Path:
    name = (
        "memory_preflight.json"
        if artifact_type == "memory_preflight"
        else "context_packet.json"
    )
    return session_artifact_dir(state_root, project, session_id) / name


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def digest_payload(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _atomic_write_bytes(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(raw)
    os.replace(tmp, path)


def persist_preflight_artifact(
    state_root: Path,
    preflight: MemoryPreflight,
) -> tuple[MemoryPreflight, SessionArtifactRef, bool]:
    """Persist memory_preflight.json atomically.

    Returns (preflight_with_digest, ref, created).
    On identical digest retry → reuse (created=False).
    On conflicting digest → ArtifactConflictError.
    """
    path = artifact_path(
        state_root, preflight.repo, preflight.session_id, "memory_preflight"
    )
    # Digest excludes artifact_digest itself (filled after).
    body = preflight.model_dump(mode="json")
    body["artifact_digest"] = ""
    digest = digest_payload(body)
    stamped = preflight.model_copy(update={"artifact_digest": digest})
    stamped_body = stamped.model_dump(mode="json")
    raw = json.dumps(stamped_body, indent=2, ensure_ascii=False).encode("utf-8")

    if path.is_file():
        existing_raw = path.read_bytes()
        try:
            existing = MemoryPreflight.model_validate(json.loads(existing_raw.decode("utf-8")))
        except (json.JSONDecodeError, ValueError) as exc:
            raise ArtifactConflictError(
                f"corrupt memory_preflight at {path}: {exc}"
            ) from exc
        if existing.artifact_digest == digest or digest_payload(
            {**existing.model_dump(mode="json"), "artifact_digest": ""}
        ) == digest:
            ref = SessionArtifactRef(
                artifact_type="memory_preflight",
                relative_path=_relative_to_state(state_root, path),
                digest=existing.artifact_digest or digest,
                byte_size=len(existing_raw),
                schema_name=existing.schema_version,
                created_at=existing.created_at,
            )
            return existing, ref, False
        raise ArtifactConflictError(
            f"memory_preflight digest conflict for session {preflight.session_id}: "
            f"existing={existing.artifact_digest!r} candidate={digest!r}"
        )

    _atomic_write_bytes(path, raw)
    ref = SessionArtifactRef(
        artifact_type="memory_preflight",
        relative_path=_relative_to_state(state_root, path),
        digest=digest,
        byte_size=len(raw),
        schema_name=stamped.schema_version,
        created_at=stamped.created_at,
    )
    return stamped, ref, True


def persist_context_packet_artifact(
    state_root: Path,
    packet: ContextPacket,
) -> tuple[ContextPacket, SessionArtifactRef, bool]:
    """Persist context_packet.json atomically (same idempotency rules)."""
    path = artifact_path(state_root, packet.repo, packet.session_id, "context_packet")
    body = packet.model_dump(mode="json")
    body["artifact_digest"] = ""
    digest = digest_payload(body)
    stamped = packet.model_copy(update={"artifact_digest": digest})
    stamped_body = stamped.model_dump(mode="json")
    raw = json.dumps(stamped_body, indent=2, ensure_ascii=False).encode("utf-8")

    if path.is_file():
        existing_raw = path.read_bytes()
        try:
            existing = ContextPacket.model_validate(json.loads(existing_raw.decode("utf-8")))
        except (json.JSONDecodeError, ValueError) as exc:
            raise ArtifactConflictError(
                f"corrupt context_packet at {path}: {exc}"
            ) from exc
        if existing.artifact_digest == digest or digest_payload(
            {**existing.model_dump(mode="json"), "artifact_digest": ""}
        ) == digest:
            ref = SessionArtifactRef(
                artifact_type="context_packet",
                relative_path=_relative_to_state(state_root, path),
                digest=existing.artifact_digest or digest,
                byte_size=len(existing_raw),
                schema_name=existing.schema_version,
                created_at=existing.created_at,
            )
            return existing, ref, False
        raise ArtifactConflictError(
            f"context_packet digest conflict for session {packet.session_id}: "
            f"existing={existing.artifact_digest!r} candidate={digest!r}"
        )

    _atomic_write_bytes(path, raw)
    ref = SessionArtifactRef(
        artifact_type="context_packet",
        relative_path=_relative_to_state(state_root, path),
        digest=digest,
        byte_size=len(raw),
        schema_name=stamped.schema_version,
        created_at=stamped.created_at,
    )
    return stamped, ref, True


def _relative_to_state(state_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(state_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def load_preflight_artifact(
    state_root: Path, project: str, session_id: str
) -> MemoryPreflight | None:
    path = artifact_path(state_root, project, session_id, "memory_preflight")
    if not path.is_file():
        return None
    try:
        return MemoryPreflight.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValueError):
        return None


def load_context_packet_artifact(
    state_root: Path, project: str, session_id: str
) -> ContextPacket | None:
    path = artifact_path(state_root, project, session_id, "context_packet")
    if not path.is_file():
        return None
    try:
        return ContextPacket.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValueError):
        return None


def context_pack_digest(pack: Any) -> str:
    """Stable digest of a ContextPack (or dict)."""
    if hasattr(pack, "model_dump"):
        payload = pack.model_dump(mode="json")
    else:
        payload = dict(pack)
    return digest_payload(payload)
