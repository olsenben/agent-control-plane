"""V9 T07 -- artifact dispositions (metadata_only | redacted_text_view |
downloadable_redacted_copy), H5 artifact trust.

Covers:

- ``artifact_id_for`` is opaque, stable, and derived only from server-known
  values -- never the filesystem path.
- ``resolve_artifact_ref`` maps an opaque id back to the session's own ref;
  an unknown/forged id resolves to ``None``.
- Trust gates: path escape, symlink rejection, size mismatch, MIME
  rejection, digest mismatch all fail closed to "not available" -- never
  raise past this module's public functions.
- Redaction: secret-shaped keys become ``<redacted>`` in both the text
  view and the download copy; the original raw bytes are never returned.
- End-to-end via routes: view/download endpoints enforce the same auth
  matrix as every other run_id-keyed route, never accept a path from the
  request, and default to no raw download.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_control.observe.artifacts import (
    ArtifactGateError,
    artifact_disposition_rows,
    artifact_id_for,
    build_redacted_copy,
    get_redacted_download,
    get_redacted_text_view,
    resolve_artifact_ref,
)
from agent_control.session.storage import persist_session_with_run_index
from agent_control.webhook_server import create_app
from agent_shared.models.agent_session import AgentSession, SessionStatus
from agent_shared.models.memory_preflight import SessionArtifactRef

PROJECT = "ai-sdlc-lab/demo-app"
SECRET_VALUE = "super-secret-token-value-should-never-be-exposed"


def _write_artifact_json(state_root: Path, relative_dir: str, filename: str, body: dict) -> tuple[Path, str, int]:
    directory = state_root / relative_dir
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    raw = json.dumps(body, indent=2).encode("utf-8")
    path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    return path, digest, len(raw)


def _seed_session_with_artifact(
    state_root: Path,
    *,
    run_id: str,
    session_id: str,
    artifact_body: dict,
    artifact_filename: str = "memory_preflight.json",
) -> tuple[AgentSession, SessionArtifactRef]:
    path, digest, byte_size = _write_artifact_json(
        state_root,
        f"projects/ai-sdlc-lab/demo-app/sessions/artifacts/{session_id}",
        artifact_filename,
        artifact_body,
    )
    ref = SessionArtifactRef(
        artifact_type="memory_preflight",
        relative_path=path.resolve().relative_to(state_root.resolve()).as_posix(),
        digest=digest,
        byte_size=byte_size,
        schema_name="memory_preflight.v1",
        created_at="2026-07-22T00:00:00+00:00",
    )
    session = AgentSession(
        session_id=session_id,
        project=PROJECT,
        repo=PROJECT.split("/", 1)[1],
        subject_kind="issue",
        subject_number=12,
        command_kind="review",
        status=SessionStatus.RUNNING,
        run_ids=[run_id],
        correlation_id=f"corr-{session_id}",
        trace_id=f"tr-{session_id}",
        input_state_sha="a" * 64,
        head_sha="b" * 40,
        policy_source_sha="c" * 40,
        risk_level="risk1",
        risk_tags=["needs_review"],
        invoked_by="tester",
        created_at="2026-07-22T00:00:00+00:00",
        updated_at="2026-07-22T00:05:00+00:00",
        memory_preflight=ref,
    )
    persist_session_with_run_index(state_root, session)
    return session, ref


def _app(tmp_path: Path, monkeypatch, **env):
    monkeypatch.setenv("AGENT_STATE_ROOT", str(tmp_path))
    monkeypatch.setenv("OBSERVE_REQUIRE_AUTH", "false")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return create_app()


_SAFE_BODY = {
    "schema_version": "memory_preflight.v1",
    "session_id": "placeholder",
    "status": "complete",
    "auth_header": SECRET_VALUE,
    "nested": {"api_key": SECRET_VALUE, "note": "kept"},
}


# --- artifact_id_for / resolve_artifact_ref --------------------------------


def test_artifact_id_is_opaque_and_stable() -> None:
    id_a = artifact_id_for("sess-1", "memory_preflight", "d" * 64)
    id_b = artifact_id_for("sess-1", "memory_preflight", "d" * 64)
    assert id_a == id_b
    assert "sess-1" not in id_a
    assert "memory_preflight" not in id_a
    assert len(id_a) == 32


def test_artifact_id_differs_for_different_inputs() -> None:
    id_a = artifact_id_for("sess-1", "memory_preflight", "d" * 64)
    id_b = artifact_id_for("sess-2", "memory_preflight", "d" * 64)
    id_c = artifact_id_for("sess-1", "context_packet", "d" * 64)
    assert len({id_a, id_b, id_c}) == 3


def test_resolve_artifact_ref_finds_known_ref(tmp_path: Path) -> None:
    session, ref = _seed_session_with_artifact(
        tmp_path, run_id="run-t07-resolve", session_id="sess-t07-resolve", artifact_body=_SAFE_BODY
    )
    artifact_id = artifact_id_for(session.session_id, ref.artifact_type, ref.digest)
    resolved = resolve_artifact_ref(session, artifact_id)
    assert resolved is not None
    kind, resolved_ref = resolved
    assert kind == "memory_preflight"
    assert resolved_ref.digest == ref.digest


def test_resolve_artifact_ref_rejects_unknown_id(tmp_path: Path) -> None:
    session, _ref = _seed_session_with_artifact(
        tmp_path, run_id="run-t07-unknown", session_id="sess-t07-unknown", artifact_body=_SAFE_BODY
    )
    assert resolve_artifact_ref(session, "forged-artifact-id-0000000000000") is None
    assert resolve_artifact_ref(session, "") is None


# --- redaction --------------------------------------------------------------


def test_build_redacted_copy_redacts_secret_shaped_keys() -> None:
    raw = json.dumps(_SAFE_BODY).encode("utf-8")
    redacted = build_redacted_copy(raw)
    assert redacted["auth_header"] == "<redacted>"
    assert redacted["nested"]["api_key"] == "<redacted>"
    assert redacted["nested"]["note"] == "kept"
    assert redacted["status"] == "complete"
    # The secret value itself must not survive anywhere in the structure.
    assert SECRET_VALUE not in json.dumps(redacted)


# --- get_redacted_text_view / get_redacted_download ------------------------


def test_get_redacted_text_view_never_contains_secret(tmp_path: Path) -> None:
    session, ref = _seed_session_with_artifact(
        tmp_path, run_id="run-t07-view", session_id="sess-t07-view", artifact_body=_SAFE_BODY
    )
    artifact_id = artifact_id_for(session.session_id, ref.artifact_type, ref.digest)
    view = get_redacted_text_view(session, tmp_path, artifact_id)
    assert view is not None
    assert SECRET_VALUE not in view.text
    assert "<redacted>" in view.text
    assert "complete" in view.text


def test_get_redacted_download_never_returns_raw_bytes(tmp_path: Path) -> None:
    session, ref = _seed_session_with_artifact(
        tmp_path, run_id="run-t07-download", session_id="sess-t07-download", artifact_body=_SAFE_BODY
    )
    artifact_id = artifact_id_for(session.session_id, ref.artifact_type, ref.digest)
    original_bytes = (
        tmp_path / "projects/ai-sdlc-lab/demo-app/sessions/artifacts/sess-t07-download/memory_preflight.json"
    ).read_bytes()
    download = get_redacted_download(session, tmp_path, artifact_id)
    assert download is not None
    assert SECRET_VALUE.encode() not in download.content
    assert download.content != original_bytes
    assert download.filename == "memory_preflight-redacted.json"
    parsed = json.loads(download.content)
    assert parsed["auth_header"] == "<redacted>"


def test_get_redacted_view_returns_none_for_unknown_artifact_id(tmp_path: Path) -> None:
    session, _ref = _seed_session_with_artifact(
        tmp_path, run_id="run-t07-none", session_id="sess-t07-none", artifact_body=_SAFE_BODY
    )
    assert get_redacted_text_view(session, tmp_path, "does-not-exist") is None
    assert get_redacted_download(session, tmp_path, "does-not-exist") is None


# --- trust gates -------------------------------------------------------------


def test_gate_fails_closed_on_digest_mismatch(tmp_path: Path) -> None:
    session, ref = _seed_session_with_artifact(
        tmp_path, run_id="run-t07-digest", session_id="sess-t07-digest", artifact_body=_SAFE_BODY
    )
    tampered = ref.model_copy(update={"digest": "0" * 64})
    session.memory_preflight = tampered
    artifact_id = artifact_id_for(session.session_id, tampered.artifact_type, tampered.digest)
    assert get_redacted_text_view(session, tmp_path, artifact_id) is None


def test_gate_fails_closed_on_size_mismatch(tmp_path: Path) -> None:
    session, ref = _seed_session_with_artifact(
        tmp_path, run_id="run-t07-size", session_id="sess-t07-size", artifact_body=_SAFE_BODY
    )
    tampered = ref.model_copy(update={"byte_size": ref.byte_size + 1000})
    session.memory_preflight = tampered
    artifact_id = artifact_id_for(session.session_id, tampered.artifact_type, tampered.digest)
    assert get_redacted_text_view(session, tmp_path, artifact_id) is None


def test_gate_fails_closed_on_disallowed_suffix(tmp_path: Path) -> None:
    session, ref = _seed_session_with_artifact(
        tmp_path,
        run_id="run-t07-mime",
        session_id="sess-t07-mime",
        artifact_body=_SAFE_BODY,
        artifact_filename="memory_preflight.txt",
    )
    artifact_id = artifact_id_for(session.session_id, ref.artifact_type, ref.digest)
    assert get_redacted_text_view(session, tmp_path, artifact_id) is None


def test_gate_fails_closed_on_missing_file(tmp_path: Path) -> None:
    session, ref = _seed_session_with_artifact(
        tmp_path, run_id="run-t07-missing", session_id="sess-t07-missing", artifact_body=_SAFE_BODY
    )
    path = tmp_path / "projects/ai-sdlc-lab/demo-app/sessions/artifacts/sess-t07-missing/memory_preflight.json"
    path.unlink()
    artifact_id = artifact_id_for(session.session_id, ref.artifact_type, ref.digest)
    assert get_redacted_text_view(session, tmp_path, artifact_id) is None


def test_gate_rejects_symlinked_artifact_file(tmp_path: Path) -> None:
    session, ref = _seed_session_with_artifact(
        tmp_path, run_id="run-t07-symlink", session_id="sess-t07-symlink", artifact_body=_SAFE_BODY
    )
    path = tmp_path / "projects/ai-sdlc-lab/demo-app/sessions/artifacts/sess-t07-symlink/memory_preflight.json"
    outside_target = tmp_path.parent / "outside_artifact_target.json"
    outside_target.write_bytes(path.read_bytes())
    real_bytes = path.read_bytes()
    path.unlink()
    try:
        path.symlink_to(outside_target)
    except OSError:
        pytest.skip("symlinks not supported in this environment")
    assert path.read_bytes() == real_bytes  # symlink points at equivalent content
    artifact_id = artifact_id_for(session.session_id, ref.artifact_type, ref.digest)
    assert get_redacted_text_view(session, tmp_path, artifact_id) is None
    assert get_redacted_download(session, tmp_path, artifact_id) is None


def test_gate_rejects_path_escape_outside_state_root(tmp_path: Path) -> None:
    session, ref = _seed_session_with_artifact(
        tmp_path, run_id="run-t07-escape", session_id="sess-t07-escape", artifact_body=_SAFE_BODY
    )
    escaping = ref.model_copy(update={"relative_path": "../outside_state_root.json"})
    (tmp_path.parent / "outside_state_root.json").write_bytes(b"{}")
    session.memory_preflight = escaping
    artifact_id = artifact_id_for(session.session_id, escaping.artifact_type, escaping.digest)
    assert get_redacted_text_view(session, tmp_path, artifact_id) is None


# --- artifact_disposition_rows (panel 5 view-model) -------------------------


def test_disposition_rows_default_to_metadata_only_and_probe_availability(tmp_path: Path) -> None:
    session, _ref = _seed_session_with_artifact(
        tmp_path, run_id="run-t07-rows", session_id="sess-t07-rows", artifact_body=_SAFE_BODY
    )
    rows = artifact_disposition_rows(session, tmp_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["disposition"] == "metadata_only"
    assert row["text_view_available"] is True
    assert row["download_available"] is True
    assert "artifact_id" in row and row["artifact_id"]


def test_disposition_rows_empty_for_session_without_artifacts(tmp_path: Path) -> None:
    session = AgentSession(
        session_id="sess-t07-no-artifacts",
        project=PROJECT,
        repo=PROJECT.split("/", 1)[1],
        subject_kind="issue",
        subject_number=13,
        command_kind="review",
        status=SessionStatus.RUNNING,
        run_ids=["run-t07-no-artifacts"],
        correlation_id="corr-x",
        trace_id="tr-x",
        input_state_sha="a" * 64,
        head_sha="b" * 40,
        policy_source_sha="c" * 40,
        risk_level="risk1",
        invoked_by="tester",
        created_at="2026-07-22T00:00:00+00:00",
        updated_at="2026-07-22T00:00:00+00:00",
    )
    assert artifact_disposition_rows(session, tmp_path) == []


# --- ArtifactGateError never escapes public functions -----------------------


def test_artifact_gate_error_carries_generic_reason_code() -> None:
    err = ArtifactGateError("digest_mismatch")
    assert err.reason_code == "digest_mismatch"
    assert str(err) == "digest_mismatch"


# --- end-to-end via routes ---------------------------------------------------


def test_route_view_and_download_never_accept_a_path_from_request(tmp_path: Path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    run_id = "run-t07-route-view"
    session_id = "sess-t07-route-view"
    session, ref = _seed_session_with_artifact(tmp_path, run_id=run_id, session_id=session_id, artifact_body=_SAFE_BODY)
    artifact_id = artifact_id_for(session.session_id, ref.artifact_type, ref.digest)
    client = TestClient(app)

    resp = client.get(f"/observe/sessions/{run_id}/artifacts/{artifact_id}/view")
    assert resp.status_code == 200
    assert SECRET_VALUE not in resp.text
    assert "&lt;redacted&gt;" in resp.text or "<redacted>" in resp.text

    download = client.get(f"/observe/sessions/{run_id}/artifacts/{artifact_id}/download")
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("application/json")
    assert "attachment" in download.headers["content-disposition"]
    assert SECRET_VALUE.encode() not in download.content

    # A path-shaped or otherwise-forged artifact_id must never resolve to a
    # file -- this route resolves only through the session's own refs.
    escape_attempt = client.get(
        f"/observe/sessions/{run_id}/artifacts/..%2F..%2F..%2Fetc%2Fpasswd/view"
    )
    assert escape_attempt.status_code == 404


def test_route_artifact_view_requires_auth(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_STATE_ROOT", str(tmp_path))
    monkeypatch.setenv("OBSERVE_REQUIRE_AUTH", "true")
    monkeypatch.delenv("OBSERVE_SHARED_TOKEN", raising=False)
    app = create_app()
    run_id = "run-t07-route-auth"
    session_id = "sess-t07-route-auth"
    session, ref = _seed_session_with_artifact(tmp_path, run_id=run_id, session_id=session_id, artifact_body=_SAFE_BODY)
    artifact_id = artifact_id_for(session.session_id, ref.artifact_type, ref.digest)
    client = TestClient(app)

    resp = client.get(f"/observe/sessions/{run_id}/artifacts/{artifact_id}/view")
    assert resp.status_code == 401

    resp2 = client.get(f"/observe/sessions/{run_id}/artifacts/{artifact_id}/download")
    assert resp2.status_code == 401


def test_route_artifact_view_404_for_unknown_artifact_id(tmp_path: Path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    run_id = "run-t07-route-404"
    session_id = "sess-t07-route-404"
    _seed_session_with_artifact(tmp_path, run_id=run_id, session_id=session_id, artifact_body=_SAFE_BODY)
    client = TestClient(app)
    resp = client.get(f"/observe/sessions/{run_id}/artifacts/not-a-real-id/view")
    assert resp.status_code == 404
    resp2 = client.get(f"/observe/sessions/{run_id}/artifacts/not-a-real-id/download")
    assert resp2.status_code == 404


def test_panel_five_renders_view_and_download_links(tmp_path: Path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    run_id = "run-t07-panel5"
    session_id = "sess-t07-panel5"
    session, ref = _seed_session_with_artifact(tmp_path, run_id=run_id, session_id=session_id, artifact_body=_SAFE_BODY)
    artifact_id = artifact_id_for(session.session_id, ref.artifact_type, ref.digest)
    client = TestClient(app)
    resp = client.get(f"/observe/sessions/{run_id}")
    assert resp.status_code == 200
    body = resp.text
    assert f"/observe/sessions/{run_id}/artifacts/{artifact_id}/view" in body
    assert f"/observe/sessions/{run_id}/artifacts/{artifact_id}/download" in body
    assert "metadata-only" in body.lower()
    # The raw secret from the underlying artifact file must never leak into
    # the listing page itself (only digest/size/path/schema/created_at).
    assert SECRET_VALUE not in body
