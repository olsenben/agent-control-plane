"""Tests for immutable patch-bundle inbox (V4.1.1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_shared.bundles.inbox import (
    BundleError,
    copy_bundle_to_snapshot,
    load_ready_bundle,
    write_ready_bundle,
)
from agent_shared.models.bundle import PRODUCER_PROTOCOL_V1


def test_write_and_load_ready_bundle(tmp_path: Path) -> None:
    manifest = write_ready_bundle(
        tmp_path,
        run_id="run-abc",
        kind="fix",
        attempt_id="1",
        producer_base_sha="deadbeef" * 5,
        patch_bytes=b"diff --git a/x b/x\n+hello\n",
        producer_tree_sha="treesha",
        gate_snapshot={"passed": True},
        result_payload={"summary": "ok"},
    )
    assert manifest.producer_protocol == PRODUCER_PROTOCOL_V1
    assert manifest.patch_size > 0

    loaded, root = load_ready_bundle(
        tmp_path,
        run_id="run-abc",
        kind="fix",
        attempt_id="1",
        bundle_id=manifest.bundle_id,
    )
    assert loaded.patch_sha256 == manifest.patch_sha256
    assert (root / "READY").is_file()


def test_reject_symlink_patch(tmp_path: Path) -> None:
    manifest = write_ready_bundle(
        tmp_path,
        run_id="run-sym",
        kind="fix",
        attempt_id="1",
        producer_base_sha="a" * 40,
        patch_bytes=b"diff --git a/x b/x\n+hi\n",
    )
    root = (
        tmp_path
        / "bundle-inbox"
        / "run-sym"
        / "fix"
        / "1"
        / manifest.bundle_id
    )
    patch = root / "patch.diff"
    patch.unlink()
    outside = tmp_path / "outside_target"
    outside.write_text("x", encoding="utf-8")
    try:
        patch.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks not supported")
    with pytest.raises(BundleError, match="Symlink|hash|regular"):
        load_ready_bundle(
            tmp_path,
            run_id="run-sym",
            kind="fix",
            attempt_id="1",
            bundle_id=manifest.bundle_id,
        )


def test_reject_hash_mismatch(tmp_path: Path) -> None:
    manifest = write_ready_bundle(
        tmp_path,
        run_id="run-hash",
        kind="fix",
        attempt_id="1",
        producer_base_sha="b" * 40,
        patch_bytes=b"diff --git a/x b/x\n+one\n",
    )
    root = (
        tmp_path
        / "bundle-inbox"
        / "run-hash"
        / "fix"
        / "1"
        / manifest.bundle_id
    )
    (root / "patch.diff").write_bytes(b"diff --git a/x b/x\n+tampered\n")
    with pytest.raises(BundleError, match="hash"):
        load_ready_bundle(
            tmp_path,
            run_id="run-hash",
            kind="fix",
            attempt_id="1",
            bundle_id=manifest.bundle_id,
        )


def test_reject_partial_without_ready(tmp_path: Path) -> None:
    dest = tmp_path / "bundle-inbox" / "run-x" / "fix" / "1" / "bundle1"
    dest.mkdir(parents=True)
    (dest / "manifest.json").write_text("{}", encoding="utf-8")
    (dest / "patch.diff").write_bytes(b"x")
    with pytest.raises(BundleError, match="READY"):
        load_ready_bundle(
            tmp_path,
            run_id="run-x",
            kind="fix",
            attempt_id="1",
            bundle_id="bundle1",
        )


def test_oversized_patch_rejected(tmp_path: Path) -> None:
    with pytest.raises(BundleError, match="max size"):
        write_ready_bundle(
            tmp_path,
            run_id="run-big",
            kind="fix",
            attempt_id="1",
            producer_base_sha="c" * 40,
            patch_bytes=b"x" * 100,
            max_patch_bytes=10,
        )


def test_duplicate_bundle_id_rejected(tmp_path: Path) -> None:
    m1 = write_ready_bundle(
        tmp_path,
        run_id="run-dup",
        kind="fix",
        attempt_id="1",
        bundle_id="fixedid",
        producer_base_sha="d" * 40,
        patch_bytes=b"diff --git a/x b/x\n+a\n",
    )
    assert m1.bundle_id == "fixedid"
    with pytest.raises(BundleError, match="already exists"):
        write_ready_bundle(
            tmp_path,
            run_id="run-dup",
            kind="fix",
            attempt_id="1",
            bundle_id="fixedid",
            producer_base_sha="d" * 40,
            patch_bytes=b"diff --git a/x b/x\n+b\n",
        )


def test_two_repair_attempts_same_run(tmp_path: Path) -> None:
    a = write_ready_bundle(
        tmp_path,
        run_id="run-r",
        kind="repair",
        attempt_id="1",
        producer_base_sha="e" * 40,
        patch_bytes=b"diff --git a/x b/x\n+1\n",
    )
    b = write_ready_bundle(
        tmp_path,
        run_id="run-r",
        kind="repair",
        attempt_id="2",
        producer_base_sha="e" * 40,
        patch_bytes=b"diff --git a/x b/x\n+2\n",
    )
    assert a.bundle_id != b.bundle_id


def test_snapshot_copy_isolated(tmp_path: Path) -> None:
    manifest = write_ready_bundle(
        tmp_path,
        run_id="run-snap",
        kind="fix",
        attempt_id="1",
        producer_base_sha="f" * 40,
        patch_bytes=b"diff --git a/x b/x\n+snap\n",
    )
    snap = copy_bundle_to_snapshot(
        tmp_path,
        run_id="run-snap",
        kind="fix",
        attempt_id="1",
        bundle_id=manifest.bundle_id,
    )
    assert (snap / "patch.diff").is_file()
    # Mutating inbox after snapshot must not change snapshot bytes
    inbox_patch = (
        tmp_path
        / "bundle-inbox"
        / "run-snap"
        / "fix"
        / "1"
        / manifest.bundle_id
        / "patch.diff"
    )
    inbox_patch.write_bytes(b"TAMPERED")
    assert (snap / "patch.diff").read_bytes() != b"TAMPERED"


def test_invalid_id_rejected(tmp_path: Path) -> None:
    with pytest.raises(BundleError, match="Invalid"):
        write_ready_bundle(
            tmp_path,
            run_id="../evil",
            kind="fix",
            attempt_id="1",
            producer_base_sha="a" * 40,
            patch_bytes=b"diff\n",
        )
