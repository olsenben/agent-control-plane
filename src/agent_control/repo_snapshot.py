"""Repo snapshot jobs (explicit file/diff inspection)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def snapshot_repo(
    owner: str,
    repo: str,
    ref: str,
    workdir: Path,
) -> dict[str, Any]:
    """Stub: clone/checkout and emit snapshot metadata."""
    return {
        "owner": owner,
        "repo": repo,
        "ref": ref,
        "workdir": str(workdir),
        "status": "stub",
    }
