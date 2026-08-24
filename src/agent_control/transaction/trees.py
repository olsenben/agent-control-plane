"""Materialize exact SOURCE and CANDIDATE trees for live P2 scans.

SOURCE is the producer SHA working tree. CANDIDATE is SOURCE plus the sealed
patch. Scanners receive these directories, not a mutable workspace. Clone/fetch
reuses the existing exact-SHA read-only git path. Scanner env is not given
Gitea write, capability, or broker credentials.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from agent_shared.git_patch import git_run
from agent_shared.hash_utils import canonical_json_hash

SOURCE_DIRNAME = "source"
CANDIDATE_DIRNAME = "candidate"
TREE_DIGESTS_FILENAME = "tree_digests.json"
SOURCE_TREE_DIGEST = "SOURCE_TREE_DIGEST"
CANDIDATE_TREE_DIGEST = "CANDIDATE_TREE_DIGEST"


class TreeMaterializeError(RuntimeError):
    """Fail-closed tree materialization (missing SHA, apply failure, unbound repo)."""

    def __init__(self, reason: str, message: str = "") -> None:
        self.reason = reason
        super().__init__(message or reason)


@dataclass(frozen=True)
class MaterializedTrees:
    source_root: Path
    candidate_root: Path
    source_tree_digest: str | None
    candidate_tree_digest: str | None
    source_ready: bool
    candidate_ready: bool
    error: str | None = None

    def p2_kwargs(self) -> dict[str, str]:
        """Always include intended tree paths. Missing dirs fail-closed in P2."""
        return {
            "source_root": str(self.source_root),
            "candidate_root": str(self.candidate_root),
        }


def tree_content_digest(root: Path) -> str:
    """SHA-256 of the sorted (path, file digest) list. Excludes .git."""
    if not root.is_dir():
        raise TreeMaterializeError("missing_tree", f"tree root missing: {root}")
    entries: list[dict[str, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(root).as_posix()
        if rel == ".git" or rel.startswith(".git/"):
            continue
        entries.append({"path": rel, "sha256": _file_sha256(path)})
    return canonical_json_hash(entries)


def write_tree_digest_receipt(
    dest: Path,
    *,
    source_tree_digest: str | None,
    candidate_tree_digest: str | None,
    source_sha: str,
    patch_digest: str | None = None,
    readonly_intended: bool = True,
    extra: dict[str, Any] | None = None,
) -> Path:
    payload: dict[str, Any] = {
        SOURCE_TREE_DIGEST: source_tree_digest,
        CANDIDATE_TREE_DIGEST: candidate_tree_digest,
        "source_sha": source_sha,
        "patch_digest": patch_digest,
        "readonly_intended": readonly_intended,
    }
    if extra:
        payload.update(extra)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, dest)
    return dest


def materialize_source_candidate_trees(
    *,
    bundle_root: Path,
    source_sha: str,
    patch_path: Path,
        repo_url: str | None = None,
        project: str | None = None,
        settings: Any | None = None,
        work_dir: Path | None = None,
        patch_digest: str | None = None,
        receipt_dir: Path | None = None,
    ) -> MaterializedTrees:
    """Write bundle_root/source and bundle_root/candidate as read-only-intended trees.

    candidate = exact source SHA working tree + sealed patch apply.
    A failed patch does not leave candidate as a copy of source.
    """
    source_root = bundle_root / SOURCE_DIRNAME
    candidate_root = bundle_root / CANDIDATE_DIRNAME
    receipt_root = receipt_dir or bundle_root
    sha = (source_sha or "").strip()
    if not sha:
        return MaterializedTrees(
            source_root=source_root,
            candidate_root=candidate_root,
            source_tree_digest=None,
            candidate_tree_digest=None,
            source_ready=False,
            candidate_ready=False,
            error="missing_sha",
        )
    if not patch_path.is_file():
        return MaterializedTrees(
            source_root=source_root,
            candidate_root=candidate_root,
            source_tree_digest=None,
            candidate_tree_digest=None,
            source_ready=False,
            candidate_ready=False,
            error="patch_missing",
        )
    resolved = (repo_url or "").strip() or _resolve_repo_url(
        settings=settings, project=project
    )
    if not resolved:
        return MaterializedTrees(
            source_root=source_root,
            candidate_root=candidate_root,
            source_tree_digest=None,
            candidate_tree_digest=None,
            source_ready=False,
            candidate_ready=False,
            error="unbound_repo",
        )
    existing = _reuse_if_matching(
        receipt_root,
        source_root=source_root,
        candidate_root=candidate_root,
        source_sha=sha,
        patch_digest=patch_digest,
    )
    if existing is not None:
        return existing
    work = Path(work_dir) if work_dir is not None else bundle_root / ".source-work"
    try:
        checkout = _checkout_source_sha(
            repo_url=resolved,
            source_sha=sha,
            dest=work,
            settings=settings,
        )
        _ensure_writable(source_root)
        _copy_working_tree(checkout, source_root)
        source_digest = tree_content_digest(source_root)
        _ensure_writable(candidate_root)
        if candidate_root.exists():
            shutil.rmtree(candidate_root)
        _copy_working_tree(source_root, candidate_root)
        try:
            _apply_sealed_patch(candidate_root, patch_path)
        except TreeMaterializeError as exc:
            _remove_tree(candidate_root)
            _mark_readonly_intended(source_root)
            write_tree_digest_receipt(
                receipt_root / TREE_DIGESTS_FILENAME,
                source_tree_digest=source_digest,
                candidate_tree_digest=None,
                source_sha=sha,
                patch_digest=patch_digest,
            )
            return MaterializedTrees(
                source_root=source_root,
                candidate_root=candidate_root,
                source_tree_digest=source_digest,
                candidate_tree_digest=None,
                source_ready=True,
                candidate_ready=False,
                error=exc.reason,
            )
        candidate_digest = tree_content_digest(candidate_root)
        if candidate_digest == source_digest and _patch_changes_files(patch_path):
            _remove_tree(candidate_root)
            _mark_readonly_intended(source_root)
            write_tree_digest_receipt(
                receipt_root / TREE_DIGESTS_FILENAME,
                source_tree_digest=source_digest,
                candidate_tree_digest=None,
                source_sha=sha,
                patch_digest=patch_digest,
            )
            return MaterializedTrees(
                source_root=source_root,
                candidate_root=candidate_root,
                source_tree_digest=source_digest,
                candidate_tree_digest=None,
                source_ready=True,
                candidate_ready=False,
                error="candidate_reused_source",
            )
        _mark_readonly_intended(source_root)
        _mark_readonly_intended(candidate_root)
        write_tree_digest_receipt(
            receipt_root / TREE_DIGESTS_FILENAME,
            source_tree_digest=source_digest,
            candidate_tree_digest=candidate_digest,
            source_sha=sha,
            patch_digest=patch_digest,
        )
        return MaterializedTrees(
            source_root=source_root,
            candidate_root=candidate_root,
            source_tree_digest=source_digest,
            candidate_tree_digest=candidate_digest,
            source_ready=True,
            candidate_ready=True,
        )
    except (TreeMaterializeError, OSError) as exc:
        _remove_tree(candidate_root)
        reason = getattr(exc, "reason", None) or "materialize_failed"
        return MaterializedTrees(
            source_root=source_root,
            candidate_root=candidate_root,
            source_tree_digest=None,
            candidate_tree_digest=None,
            source_ready=source_root.is_dir(),
            candidate_ready=False,
            error=str(reason),
        )
    finally:
        if work_dir is None:
            _remove_tree(work)


def _file_sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_repo_url(*, settings: Any | None = None, project: str | None = None) -> str:
    if project is None:
        return ""
    try:
        from agent_control.project_registry import resolve_project

        cfg = resolve_project(project, settings=settings)
    except Exception:
        return ""
    return str(cfg.repo_url or "")


def _checkout_source_sha(
    *,
    repo_url: str,
    source_sha: str,
    dest: Path,
    settings: Any | None,
) -> Path:
    from agent_control.context.workspace import ExactShaWorkspaceError, materialize_exact_sha_workspace

    try:
        return materialize_exact_sha_workspace(
            repo_url=repo_url,
            target_sha=source_sha,
            dest=dest,
            settings=settings,
        )
    except ExactShaWorkspaceError as exc:
        raise TreeMaterializeError(exc.reason, str(exc)) from exc


def _copy_working_tree(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if item.name == ".git":
            continue
        target = dest / item.name
        if item.is_dir():
            shutil.copytree(item, target, symlinks=False)
        elif item.is_file() and not item.is_symlink():
            shutil.copy2(item, target)


def _apply_sealed_patch(candidate: Path, patch_path: Path) -> None:
    proc = git_run(
        candidate,
        ["git", "apply", "--whitespace=nowarn", str(patch_path.resolve())],
    )
    if proc.returncode != 0:
        raise TreeMaterializeError(
            "patch_apply_failed",
            (proc.stderr or proc.stdout or "git apply failed").strip(),
        )


def _patch_changes_files(patch_path: Path) -> bool:
    text = patch_path.read_text(encoding="utf-8", errors="replace")
    return any(line.startswith("+++ b/") and not line.endswith("/dev/null") for line in text.splitlines())


def _reuse_if_matching(
    receipt_root: Path,
    *,
    source_root: Path,
    candidate_root: Path,
    source_sha: str,
    patch_digest: str | None,
) -> MaterializedTrees | None:
    receipt_path = receipt_root / TREE_DIGESTS_FILENAME
    if not source_root.is_dir() or not candidate_root.is_dir() or not receipt_path.is_file():
        return None
    try:
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    if str(payload.get("source_sha") or "") != source_sha:
        return None
    if patch_digest and str(payload.get("patch_digest") or "") != patch_digest:
        return None
    source_digest = payload.get(SOURCE_TREE_DIGEST)
    candidate_digest = payload.get(CANDIDATE_TREE_DIGEST)
    if not source_digest or not candidate_digest:
        return None
    if source_digest == candidate_digest and _files_differ(source_root, candidate_root):
        return None
    return MaterializedTrees(
        source_root=source_root,
        candidate_root=candidate_root,
        source_tree_digest=str(source_digest),
        candidate_tree_digest=str(candidate_digest),
        source_ready=True,
        candidate_ready=True,
    )


def _files_differ(left: Path, right: Path) -> bool:
    try:
        return tree_content_digest(left) != tree_content_digest(right)
    except TreeMaterializeError:
        return True


def _mark_readonly_intended(root: Path) -> None:
    if os.name == "nt" or not root.exists():
        return
    for path in [root, *root.rglob("*")]:
        try:
            if path.is_dir():
                os.chmod(path, stat.S_IREAD | stat.S_IEXEC | stat.S_IRGRP | stat.S_IXGRP)
            elif path.is_file():
                os.chmod(path, stat.S_IREAD | stat.S_IRGRP)
        except OSError:
            continue


def _ensure_writable(root: Path) -> None:
    if not root.exists():
        return
    for path in [root, *root.rglob("*")]:
        try:
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
        except OSError:
            continue


def _remove_tree(path: Path) -> None:
    if not path.exists():
        return
    _ensure_writable(path)
    shutil.rmtree(path, ignore_errors=True)
