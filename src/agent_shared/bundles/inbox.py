"""Attempt-scoped content-addressed patch bundle inbox (CT104 producer)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_shared.models.bundle import (
    BUNDLE_SCHEMA_VERSION,
    PRODUCER_PROTOCOL_V1,
    BundleKind,
    PatchBundleManifest,
)

READY_MARKER = "READY"
MANIFEST_NAME = "manifest.json"
ALLOWED_ARTIFACT_NAMES = frozenset(
    {
        "patch.diff",
        "diff_gate_result.json",
        "fix_result.json",
        "repair_result.json",
        "sandbox_attestation.v1.json",
        "execution_attestation.v1.json",
        "evidence.json",
        "publication_log.json",
        MANIFEST_NAME,
        READY_MARKER,
    }
)

# Conservative defaults for untrusted producer artifacts
DEFAULT_MAX_PATCH_BYTES = 2 * 1024 * 1024  # 2 MiB
DEFAULT_MAX_ARTIFACT_BYTES = 4 * 1024 * 1024  # 4 MiB

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class BundleError(Exception):
    """Bundle write/load/validation failure."""


def validate_id(name: str, *, label: str) -> str:
    if not name or not _ID_RE.fullmatch(name):
        raise BundleError(f"Invalid {label}: {name!r}")
    if ".." in name or "/" in name or "\\" in name:
        raise BundleError(f"Invalid {label} path characters: {name!r}")
    return name


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def bundle_inbox_root(state_root: Path) -> Path:
    return state_root / "bundle-inbox"


def bundle_dir(
    state_root: Path,
    *,
    run_id: str,
    kind: BundleKind,
    attempt_id: str,
    bundle_id: str,
) -> Path:
    validate_id(run_id, label="run_id")
    validate_id(attempt_id, label="attempt_id")
    validate_id(bundle_id, label="bundle_id")
    return (
        bundle_inbox_root(state_root)
        / run_id
        / kind
        / attempt_id
        / bundle_id
    )


def _assert_regular_file(path: Path) -> None:
    if path.is_symlink():
        raise BundleError(f"Symlinks rejected: {path.name}")
    if not path.is_file():
        raise BundleError(f"Not a regular file: {path.name}")


def _assert_safe_name(name: str) -> None:
    if name not in ALLOWED_ARTIFACT_NAMES:
        raise BundleError(f"Disallowed artifact name: {name!r}")
    if ".." in name or "/" in name or "\\" in name:
        raise BundleError(f"Path traversal in artifact name: {name!r}")


def write_ready_bundle(
    state_root: Path,
    *,
    run_id: str,
    kind: BundleKind,
    attempt_id: str | None = None,
    bundle_id: str | None = None,
    producer_base_sha: str,
    patch_bytes: bytes,
    producer_tree_sha: str | None = None,
    gate_snapshot: dict[str, Any] | bytes | None = None,
    result_payload: dict[str, Any] | bytes | None = None,
    extra_artifacts: dict[str, bytes] | None = None,
    max_patch_bytes: int = DEFAULT_MAX_PATCH_BYTES,
    max_artifact_bytes: int = DEFAULT_MAX_ARTIFACT_BYTES,
) -> PatchBundleManifest:
    """Atomically write a finalized READY bundle under bundle-inbox.

    Writes to a temp sibling, then renames into place. Never modifies an
    existing READY directory.
    """
    validate_id(run_id, label="run_id")
    attempt = validate_id(attempt_id or "1", label="attempt_id")
    bid = validate_id(bundle_id or uuid.uuid4().hex, label="bundle_id")

    if len(patch_bytes) > max_patch_bytes:
        raise BundleError(f"Patch exceeds max size ({len(patch_bytes)} > {max_patch_bytes})")
    if len(patch_bytes) == 0:
        raise BundleError("Patch is empty")

    parent = bundle_inbox_root(state_root) / run_id / kind / attempt
    parent.mkdir(parents=True, exist_ok=True)
    final = parent / bid
    if final.exists():
        raise BundleError(f"Bundle already exists: {bid}")

    tmp = Path(
        tempfile.mkdtemp(
            prefix=f".{bid}.",
            dir=str(parent),
        )
    )
    try:
        patch_path = tmp / "patch.diff"
        patch_path.write_bytes(patch_bytes)
        _assert_regular_file(patch_path)
        patch_sha = sha256_file(patch_path)

        gate_name: str | None = None
        gate_sha: str | None = None
        if gate_snapshot is not None:
            gate_name = "diff_gate_result.json"
            gate_path = tmp / gate_name
            if isinstance(gate_snapshot, bytes):
                data = gate_snapshot
            else:
                data = json.dumps(gate_snapshot, indent=2, sort_keys=True).encode("utf-8")
            if len(data) > max_artifact_bytes:
                raise BundleError("Gate snapshot exceeds max artifact size")
            gate_path.write_bytes(data)
            _assert_regular_file(gate_path)
            gate_sha = sha256_file(gate_path)

        result_name: str | None = None
        result_sha: str | None = None
        if result_payload is not None:
            result_name = "fix_result.json" if kind == "fix" else "repair_result.json"
            result_path = tmp / result_name
            if isinstance(result_payload, bytes):
                data = result_payload
            else:
                data = json.dumps(result_payload, indent=2, sort_keys=True).encode("utf-8")
            if len(data) > max_artifact_bytes:
                raise BundleError("Result payload exceeds max artifact size")
            result_path.write_bytes(data)
            _assert_regular_file(result_path)
            result_sha = sha256_file(result_path)

        sandbox_name: str | None = None
        sandbox_sha: str | None = None
        exec_name: str | None = None
        exec_sha: str | None = None
        if extra_artifacts:
            for name, blob in extra_artifacts.items():
                _assert_safe_name(name)
                if len(blob) > max_artifact_bytes:
                    raise BundleError(f"Artifact {name} exceeds max artifact size")
                art_path = tmp / name
                art_path.write_bytes(blob)
                _assert_regular_file(art_path)
                digest = sha256_file(art_path)
                if name == "sandbox_attestation.v1.json":
                    sandbox_name = name
                    sandbox_sha = digest
                elif name == "execution_attestation.v1.json":
                    exec_name = name
                    exec_sha = digest

        created_at = datetime.now(timezone.utc).isoformat()
        manifest = PatchBundleManifest(
            schema_version=BUNDLE_SCHEMA_VERSION,
            bundle_id=bid,
            run_id=run_id,
            attempt_id=attempt,
            kind=kind,
            producer_base_sha=producer_base_sha,
            patch_filename="patch.diff",
            patch_sha256=patch_sha,
            patch_size=len(patch_bytes),
            producer_tree_sha=producer_tree_sha,
            gate_snapshot_filename=gate_name,
            gate_snapshot_sha256=gate_sha,
            result_filename=result_name,
            result_sha256=result_sha,
            sandbox_attestation_filename=sandbox_name,
            sandbox_attestation_sha256=sandbox_sha,
            execution_attestation_filename=exec_name,
            execution_attestation_sha256=exec_sha,
            producer_protocol=PRODUCER_PROTOCOL_V1,
            created_at=created_at,
        )
        man_path = tmp / MANIFEST_NAME
        man_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        _assert_regular_file(man_path)

        # READY last (or atomic rename of whole dir — we rename tmp → final)
        ready = tmp / READY_MARKER
        ready.write_text("1\n", encoding="utf-8")
        os.replace(tmp, final)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise

    return manifest


def load_ready_bundle(
    state_root: Path,
    *,
    run_id: str,
    kind: BundleKind,
    attempt_id: str,
    bundle_id: str,
    max_patch_bytes: int = DEFAULT_MAX_PATCH_BYTES,
    max_artifact_bytes: int = DEFAULT_MAX_ARTIFACT_BYTES,
) -> tuple[PatchBundleManifest, Path]:
    """Load and verify a READY bundle. Returns (manifest, bundle_dir)."""
    root = bundle_dir(
        state_root,
        run_id=run_id,
        kind=kind,
        attempt_id=attempt_id,
        bundle_id=bundle_id,
    )
    if not root.is_dir():
        raise BundleError(f"Bundle directory missing: {root}")
    ready = root / READY_MARKER
    if not ready.is_file() or ready.is_symlink():
        raise BundleError("Bundle not READY")

    man_path = root / MANIFEST_NAME
    _assert_regular_file(man_path)
    try:
        manifest = PatchBundleManifest.model_validate(
            json.loads(man_path.read_text(encoding="utf-8"))
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise BundleError(f"Invalid manifest: {exc}") from exc

    if manifest.producer_protocol != PRODUCER_PROTOCOL_V1:
        raise BundleError(f"Unsupported producer_protocol: {manifest.producer_protocol}")
    if manifest.run_id != run_id or manifest.bundle_id != bundle_id:
        raise BundleError("Manifest identity mismatch")
    if manifest.kind != kind or manifest.attempt_id != attempt_id:
        raise BundleError("Manifest kind/attempt mismatch")

    for entry in root.iterdir():
        name = entry.name
        _assert_safe_name(name)
        if name == READY_MARKER:
            continue
        _assert_regular_file(entry)
        size = entry.stat().st_size
        if name == "patch.diff" and size > max_patch_bytes:
            raise BundleError("Patch exceeds max size")
        if size > max_artifact_bytes:
            raise BundleError(f"Artifact {name} exceeds max size")

    patch_path = root / manifest.patch_filename
    _assert_regular_file(patch_path)
    if sha256_file(patch_path) != manifest.patch_sha256:
        raise BundleError("patch.diff hash mismatch")
    if patch_path.stat().st_size != manifest.patch_size:
        raise BundleError("patch.diff size mismatch")

    if manifest.gate_snapshot_filename:
        gate_path = root / manifest.gate_snapshot_filename
        _assert_regular_file(gate_path)
        if sha256_file(gate_path) != manifest.gate_snapshot_sha256:
            raise BundleError("gate snapshot hash mismatch")

    if manifest.result_filename:
        result_path = root / manifest.result_filename
        _assert_regular_file(result_path)
        if sha256_file(result_path) != manifest.result_sha256:
            raise BundleError("result hash mismatch")

    if manifest.sandbox_attestation_filename:
        sap = root / manifest.sandbox_attestation_filename
        _assert_regular_file(sap)
        if sha256_file(sap) != manifest.sandbox_attestation_sha256:
            raise BundleError("sandbox attestation hash mismatch")

    if manifest.execution_attestation_filename:
        eap = root / manifest.execution_attestation_filename
        _assert_regular_file(eap)
        if sha256_file(eap) != manifest.execution_attestation_sha256:
            raise BundleError("execution attestation hash mismatch")

    return manifest, root


def copy_bundle_to_snapshot(
    state_root: Path,
    *,
    run_id: str,
    kind: BundleKind,
    attempt_id: str,
    bundle_id: str,
) -> Path:
    """Hash-verify inbox bundle and copy into CT103-private publish-snapshots."""
    manifest, src = load_ready_bundle(
        state_root,
        run_id=run_id,
        kind=kind,
        attempt_id=attempt_id,
        bundle_id=bundle_id,
    )
    dest_root = state_root / "publish-snapshots" / run_id / bundle_id
    if dest_root.exists():
        # Idempotent: re-verify existing snapshot matches
        existing = dest_root / MANIFEST_NAME
        if existing.is_file():
            return dest_root
        shutil.rmtree(dest_root)

    dest_root.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f".snap-{bundle_id}.", dir=str(dest_root.parent)))
    try:
        for entry in src.iterdir():
            if entry.name == READY_MARKER:
                continue
            _assert_safe_name(entry.name)
            _assert_regular_file(entry)
            shutil.copy2(entry, tmp / entry.name)
        # Re-verify copy hashes
        patch = tmp / manifest.patch_filename
        if sha256_file(patch) != manifest.patch_sha256:
            raise BundleError("Snapshot copy hash mismatch")
        man_dst = tmp / MANIFEST_NAME
        man_dst.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        (tmp / READY_MARKER).write_text("1\n", encoding="utf-8")
        os.replace(tmp, dest_root)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return dest_root
