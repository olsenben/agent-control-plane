"""Artifact disposition contract + trust gates (V9 T07, H5: artifact trust).

Three dispositions, most to least conservative:

``metadata_only``
    Digest/size/path-name/schema-name/timestamp only, never content. This is
    the default for every artifact and the only disposition available when
    any trust gate below fails.

``redacted_text_view``
    A server-rendered, auto-escaped HTML page showing the artifact's own
    JSON content after this module's redaction pass (secret-shaped keys
    replaced, long strings truncated) -- never the original bytes.

``downloadable_redacted_copy``
    A file download of the *redacted* JSON (never the original bytes),
    served with a generic filename and ``application/json`` content type.

Hard requirements enforced end to end:

- The artifact's real filesystem path is **never** accepted from the
  request. Every read-path route takes only ``run_id`` (already
  auth-checked elsewhere) and an *opaque* ``artifact_id``; this module
  resolves ``artifact_id`` back to one of the session's own
  ``SessionArtifactRef`` entries server-side (:func:`resolve_artifact_ref`)
  -- an unrecognized ``artifact_id`` simply matches nothing, the same as a
  404, never a filesystem lookup of attacker-controlled input.
- Path gate: the resolved real path must land inside ``agent_state_root``
  (rejects ``..`` traversal and symlink redirection alike, since
  ``Path.resolve()`` follows every symlink in the chain before the
  containment check runs).
- Symlink gate: the artifact file itself must not be a symlink (checked
  directly, as an explicit second layer on top of the path-containment
  check above).
- Size gate: rejects anything over the disposition's byte cap, and
  requires the on-disk size to match the ``SessionArtifactRef.byte_size``
  recorded at persist time.
- MIME gate: only ``.json``-suffixed, UTF-8, JSON-parseable files qualify
  (matches every current ``SessionArtifactRef.artifact_type``, all of
  which are JSON documents).
- Hash verify: the on-disk sha256 digest must match
  ``SessionArtifactRef.digest`` before any content is read further --
  never displayed on a stale/corrupted/substituted file.
- Default no raw download: there is no route, disposition, or code path in
  this module that ever returns the artifact's original bytes; every
  content-bearing disposition redacts first.

Any gate failure degrades silently to ``metadata_only`` (fail closed) --
callers never see a stack trace or a raw error message, only a
:class:`ArtifactGateError` carrying a short, generic ``reason_code`` for
server-side logging.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from agent_control.observe.safe_display import is_prohibited_field_name
from agent_shared.models.agent_session import AgentSession
from agent_shared.models.memory_preflight import SessionArtifactRef

logger = logging.getLogger(__name__)

# Mirrors agent_control.observe.ui.ARTIFACT_REF_ATTRS -- the four
# SessionArtifactRef-typed attributes on AgentSession this Observatory
# already exposes (JSON artifacts endpoint, panel 5). Kept as our own
# tuple (not imported) so this module has no import-time dependency on
# agent_control.observe.ui.
ARTIFACT_REF_ATTRS: tuple[str, ...] = (
    "memory_preflight",
    "context_packet",
    "recursive_context",
    "verification",
)

ArtifactDisposition = str  # "metadata_only" | "redacted_text_view" | "downloadable_redacted_copy"

DISPOSITION_METADATA_ONLY: ArtifactDisposition = "metadata_only"
DISPOSITION_REDACTED_TEXT_VIEW: ArtifactDisposition = "redacted_text_view"
DISPOSITION_DOWNLOADABLE_REDACTED_COPY: ArtifactDisposition = "downloadable_redacted_copy"

_MAX_TEXT_VIEW_BYTES = 256 * 1024
_MAX_DOWNLOAD_BYTES = 1 * 1024 * 1024
_ALLOWED_SUFFIXES = (".json",)
_MAX_REDACTED_STR_LEN = 2000
_MAX_REDACTED_LIST_LEN = 200


class ArtifactGateError(Exception):
    """One of the path/symlink/size/MIME/hash trust gates failed.

    ``reason_code`` is a short, generic, non-identifying label (never a
    filesystem path or exception message) safe to log; it is never shown
    to the HTTP caller, who only ever sees a plain 404 (see
    :mod:`agent_control.observe.routes`) so that no gate failure ever
    distinguishes "does not exist" from "exists but failed a gate" to an
    external caller.
    """

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


def artifact_id_for(session_id: str, artifact_type: str, digest: str) -> str:
    """Opaque, stable artifact identifier -- never the filesystem path.

    Deterministic from server-known values only (session_id + the ref's own
    artifact_type + digest); a client can never construct a valid
    ``artifact_id`` for an artifact it does not already have server-side
    knowledge of, and this module never derives a filesystem path from an
    ``artifact_id`` directly -- resolution always goes back through the
    session's own ``SessionArtifactRef`` entries (:func:`resolve_artifact_ref`).
    """
    raw = f"observe_artifact_id.v1:{session_id}:{artifact_type}:{digest}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def resolve_artifact_ref(session: AgentSession, artifact_id: str) -> tuple[str, SessionArtifactRef] | None:
    """Map an opaque ``artifact_id`` back to one of *session*'s own artifact refs.

    Never accepts or derives a filesystem path from ``artifact_id`` itself
    -- it only re-derives :func:`artifact_id_for` from each known ref and
    compares. An ``artifact_id`` that does not match any current ref
    (forged, stale digest after a re-run, wrong session) simply resolves to
    ``None``, indistinguishable from "not found".
    """
    if not artifact_id:
        return None
    for name in ARTIFACT_REF_ATTRS:
        ref = getattr(session, name, None)
        if ref is None:
            continue
        if artifact_id_for(session.session_id, ref.artifact_type, ref.digest) == artifact_id:
            return name, ref
    return None


def _resolve_safe_path(state_root: Path, relative_path: str) -> Path:
    """Resolve *relative_path* under *state_root*, enforcing the path + symlink gates.

    ``relative_path`` always comes from an already-persisted
    ``SessionArtifactRef`` on the session file -- never from an HTTP
    request parameter (see module docstring). Still gated defensively here,
    since a ref's ``relative_path`` could in principle be stale, corrupted,
    or (pre-this-ticket) have escaped the intended root.
    """
    state_root_resolved = state_root.resolve()
    candidate = state_root / relative_path
    if candidate.is_symlink():
        raise ArtifactGateError("symlink_rejected")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ArtifactGateError("not_found") from exc
    try:
        resolved.relative_to(state_root_resolved)
    except ValueError as exc:
        raise ArtifactGateError("path_escape") from exc
    if resolved.is_symlink():  # pragma: no cover - resolve() already dereferences
        raise ArtifactGateError("symlink_rejected")
    return resolved


def _read_and_verify(path: Path, ref: SessionArtifactRef, *, max_bytes: int) -> bytes:
    """Size + MIME(suffix) + hash gates. Returns the verified raw bytes."""
    try:
        stat = path.stat()
    except OSError as exc:
        raise ArtifactGateError("not_found") from exc
    if stat.st_size > max_bytes:
        raise ArtifactGateError("too_large")
    if stat.st_size != ref.byte_size:
        raise ArtifactGateError("size_mismatch")
    if path.suffix.lower() not in _ALLOWED_SUFFIXES:
        raise ArtifactGateError("mime_rejected")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ArtifactGateError("read_failed") from exc
    digest = hashlib.sha256(raw).hexdigest()
    if digest != ref.digest:
        raise ArtifactGateError("digest_mismatch")
    return raw


def _parse_json(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArtifactGateError("not_valid_json") from exc


def _redact_value(value: Any) -> Any:
    """Recursive redaction: secret-shaped keys -> ``<redacted>``, long strings truncated.

    Reuses :func:`agent_control.observe.safe_display.is_prohibited_field_name`
    (the same name-based keyword filter guarding the generic
    ``observe_event.v1`` stream) so both safe-display choke points agree on
    what a "secret-shaped" field name looks like.
    """
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, val in value.items():
            if isinstance(key, str) and is_prohibited_field_name(key):
                out[key] = "<redacted>"
            else:
                out[key] = _redact_value(val)
        return out
    if isinstance(value, list):
        return [_redact_value(v) for v in value[:_MAX_REDACTED_LIST_LEN]]
    if isinstance(value, str) and len(value) > _MAX_REDACTED_STR_LEN:
        return value[:_MAX_REDACTED_STR_LEN] + "...(truncated)"
    return value


def build_redacted_copy(raw: bytes) -> Any:
    """Raw verified JSON bytes -> a fully redacted JSON-serializable value.

    Never returns the original bytes; always re-serialized from the parsed,
    redacted structure.
    """
    parsed = _parse_json(raw)
    return _redact_value(parsed)


def _max_available_disposition(
    state_root: Path,
    ref: SessionArtifactRef,
) -> tuple[bool, bool, str | None]:
    """Probe whether *ref* currently qualifies for the two content dispositions.

    Returns ``(text_view_available, download_available, reason_code)``.
    ``reason_code`` is the first gate failure encountered (generic, safe to
    log); ``None`` when every gate passed. Never raises -- any
    :class:`ArtifactGateError` here is caught and turned into "not
    available", the fail-closed default.
    """
    try:
        resolved = _resolve_safe_path(state_root, ref.relative_path)
        raw = _read_and_verify(resolved, ref, max_bytes=_MAX_DOWNLOAD_BYTES)
        _parse_json(raw)  # confirms MIME/shape without materializing a template
    except ArtifactGateError as exc:
        return False, False, exc.reason_code
    text_view_ok = len(raw) <= _MAX_TEXT_VIEW_BYTES
    return text_view_ok, True, None


def artifact_disposition_rows(session: AgentSession, state_root: Path) -> list[dict[str, Any]]:
    """Panel 5 view-model: one row per ``SessionArtifactRef``, gate-probed.

    ``disposition`` is always ``metadata_only`` here (H5: content is never
    embedded in this listing) -- ``text_view_available``/
    ``download_available`` tell the template whether to render the
    corresponding link; the routes themselves re-run every gate again on
    each actual request (this probe is advisory for the UI only, never
    trusted as an authorization decision).
    """
    rows: list[dict[str, Any]] = []
    for name in ARTIFACT_REF_ATTRS:
        ref = getattr(session, name, None)
        if ref is None:
            continue
        text_view_available, download_available, reason_code = _max_available_disposition(state_root, ref)
        rows.append(
            {
                "kind": name,
                "artifact_type": ref.artifact_type,
                "artifact_id": artifact_id_for(session.session_id, ref.artifact_type, ref.digest),
                "disposition": DISPOSITION_METADATA_ONLY,
                "digest": ref.digest,
                "byte_size": ref.byte_size,
                "schema_name": ref.schema_name,
                "relative_path": ref.relative_path,
                "created_at": ref.created_at,
                "text_view_available": text_view_available,
                "download_available": download_available,
                "gate_reason": reason_code,
            }
        )
    return rows


class RedactedTextView:
    __slots__ = ("kind", "artifact_type", "text")

    def __init__(self, *, kind: str, artifact_type: str, text: str) -> None:
        self.kind = kind
        self.artifact_type = artifact_type
        self.text = text


class RedactedDownload:
    __slots__ = ("kind", "artifact_type", "filename", "content")

    def __init__(self, *, kind: str, artifact_type: str, filename: str, content: bytes) -> None:
        self.kind = kind
        self.artifact_type = artifact_type
        self.filename = filename
        self.content = content


def get_redacted_text_view(
    session: AgentSession,
    state_root: Path,
    artifact_id: str,
) -> RedactedTextView | None:
    """``redacted_text_view`` disposition: resolve, gate, redact, return text.

    Returns ``None`` when ``artifact_id`` does not resolve to a known
    artifact ref *or* any trust gate fails (never distinguishes the two to
    the caller -- both are a plain "not available", matching the module's
    fail-closed default).
    """
    resolved_ref = resolve_artifact_ref(session, artifact_id)
    if resolved_ref is None:
        return None
    kind, ref = resolved_ref
    try:
        path = _resolve_safe_path(state_root, ref.relative_path)
        raw = _read_and_verify(path, ref, max_bytes=_MAX_TEXT_VIEW_BYTES)
        redacted = build_redacted_copy(raw)
    except ArtifactGateError as exc:
        logger.info(
            "observe_artifact_gate_denied disposition=redacted_text_view kind=%s reason=%s",
            kind,
            exc.reason_code,
        )
        return None
    text = json.dumps(redacted, indent=2, sort_keys=True, default=str, ensure_ascii=False)
    return RedactedTextView(kind=kind, artifact_type=ref.artifact_type, text=text)


def get_redacted_download(
    session: AgentSession,
    state_root: Path,
    artifact_id: str,
) -> RedactedDownload | None:
    """``downloadable_redacted_copy`` disposition: resolve, gate, redact, return bytes.

    Never the original file's bytes -- always a freshly re-serialized,
    redacted JSON document. Filename is generic (derived from
    ``artifact_type`` only, never the real relative path).
    """
    resolved_ref = resolve_artifact_ref(session, artifact_id)
    if resolved_ref is None:
        return None
    kind, ref = resolved_ref
    try:
        path = _resolve_safe_path(state_root, ref.relative_path)
        raw = _read_and_verify(path, ref, max_bytes=_MAX_DOWNLOAD_BYTES)
        redacted = build_redacted_copy(raw)
    except ArtifactGateError as exc:
        logger.info(
            "observe_artifact_gate_denied disposition=downloadable_redacted_copy kind=%s reason=%s",
            kind,
            exc.reason_code,
        )
        return None
    content = json.dumps(redacted, indent=2, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    filename = f"{ref.artifact_type}-redacted.json"
    return RedactedDownload(kind=kind, artifact_type=ref.artifact_type, filename=filename, content=content)
