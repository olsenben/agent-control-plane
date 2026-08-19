"""Adapters that construct :class:`RepoSnapshot` from production refs or an eval checkout.

Production uses ``RefResolution.target_sha`` and fails closed when that SHA is
missing. Eval compares ``git rev-parse HEAD`` to the requested SHA and does not
resolve other refs.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from agent_control.project_registry import RefResolution
from agent_shared.models.repo_snapshot import RepoSnapshot, SourceKind


class RepoSnapshotError(RuntimeError):
    """Fail-closed snapshot construction (missing SHA or HEAD mismatch)."""


def from_production(
    project: str,
    refs: RefResolution,
    workspace_path: str | Path,
    *,
    repository_url_or_key: str | None = None,
    lineage_id: str = "",
    index_generation: str = "0",
    created_at: datetime | None = None,
) -> RepoSnapshot:
    """Build a Gitea-origin snapshot from already-resolved production refs.

    Uses ``refs.target_sha`` only. Does not walk git history or guess HEAD.
    """
    target_sha = (refs.target_sha or "").strip()
    if not target_sha:
        raise RepoSnapshotError("target_sha missing; cannot construct production RepoSnapshot")
    return _build(
        repository_id=project,
        repository_url_or_key=repository_url_or_key or project,
        target_sha=target_sha,
        workspace_path=workspace_path,
        lineage_id=lineage_id,
        created_at=created_at,
        source_kind="gitea",
        index_generation=index_generation,
    )


def from_eval(
    repository_id: str,
    target_sha: str,
    workspace_path: str | Path,
    *,
    repository_url_or_key: str | None = None,
    lineage_id: str = "",
    index_generation: str = "0",
    created_at: datetime | None = None,
) -> RepoSnapshot:
    """Build an eval-origin snapshot after an exact-SHA HEAD check.

    Compares ``git rev-parse HEAD`` to ``target_sha``. Does not resolve the
    requested SHA as a ref, so a future commit cannot become reachable here.
    """
    requested = (target_sha or "").strip()
    if not requested:
        raise RepoSnapshotError("target_sha missing; cannot construct eval RepoSnapshot")
    actual = _git_head_sha(Path(workspace_path))
    if actual != requested:
        raise RepoSnapshotError(
            f"exact-SHA invariant failed: workspace HEAD {actual} != requested {requested}"
        )
    return _build(
        repository_id=repository_id,
        repository_url_or_key=repository_url_or_key or repository_id,
        target_sha=requested,
        workspace_path=workspace_path,
        lineage_id=lineage_id,
        created_at=created_at,
        source_kind="eval",
        index_generation=index_generation,
    )


def _build(
    *,
    repository_id: str,
    repository_url_or_key: str,
    target_sha: str,
    workspace_path: str | Path,
    lineage_id: str,
    created_at: datetime | None,
    source_kind: SourceKind,
    index_generation: str,
) -> RepoSnapshot:
    return RepoSnapshot(
        repository_id=repository_id,
        repository_url_or_key=repository_url_or_key,
        target_sha=target_sha,
        workspace_path=str(workspace_path),
        lineage_id=lineage_id,
        created_at=created_at or datetime.now(timezone.utc),
        source_kind=source_kind,
        index_generation=index_generation,
    )


def _git_head_sha(workspace: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(workspace), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RepoSnapshotError(
            f"exact-SHA invariant failed: cannot read HEAD in {workspace}"
        ) from exc
