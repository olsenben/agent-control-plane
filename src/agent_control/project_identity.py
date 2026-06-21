"""Canonical project identity for approval storage and lookup."""

from __future__ import annotations

import re
from pathlib import Path

from agent_shared.repo_identity import normalize_repo_full_name, split_repo_full_name

_UNSAFE_SEGMENT = re.compile(r"[^A-Za-z0-9_.-]+")


def canonical_project(project: str) -> str:
    normalized = normalize_repo_full_name(project)
    if normalized is None:
        raise ValueError(f"Invalid project identity: {project!r}")
    return normalized


def sanitize_path_segment(segment: str) -> str:
    cleaned = _UNSAFE_SEGMENT.sub("_", segment.strip())
    if not cleaned or cleaned in (".", ".."):
        raise ValueError(f"Unsafe path segment: {segment!r}")
    return cleaned


def approvals_dir(state_root: Path, project: str) -> Path:
    repo_full = canonical_project(project)
    owner, repo = split_repo_full_name(repo_full)
    return (
        state_root
        / "projects"
        / sanitize_path_segment(owner)
        / sanitize_path_segment(repo)
        / "approvals"
    )


def approval_file_path(state_root: Path, project: str, approval_target_id: str) -> Path:
    safe_id = sanitize_path_segment(approval_target_id)
    return approvals_dir(state_root, project) / f"{safe_id}.json"
