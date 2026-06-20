"""Canonical repo identity helpers."""

from __future__ import annotations

import re

_REPO_FULL_NAME = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def normalize_repo_full_name(project: str) -> str | None:
    """Return canonical owner/repo or None if not normalizable."""
    if not project or not isinstance(project, str):
        return None
    text = project.strip().rstrip("/")
    if "://" in text:
        # https://host/owner/repo or similar
        path = text.split("://", 1)[-1]
        parts = [p for p in path.split("/") if p and p not in ("api", "v1", "repos")]
        if len(parts) >= 2:
            text = "/".join(parts[-2:])
        else:
            return None
    text = text.lstrip("./")
    if text.startswith("@"):
        return None
    if "/" not in text:
        return None
    owner, repo = text.split("/", 1)
    if not owner or not repo:
        return None
    candidate = f"{owner}/{repo}"
    if not _REPO_FULL_NAME.match(candidate):
        return None
    return candidate


def split_repo_full_name(repo_full_name: str) -> tuple[str, str]:
    owner, repo = repo_full_name.split("/", 1)
    return owner, repo
