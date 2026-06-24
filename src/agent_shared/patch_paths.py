"""Shared repo-relative path validation for fix patches (Slice 6B+)."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

PROTECTED_PREFIXES: tuple[str, ...] = (
    ".gitea/",
    ".agent/",
    "docs/adr/",
)


class PatchPathError(ValueError):
    """Raised when a patch path fails validation."""


def normalize_repo_relative_path(path: str) -> str:
    """Normalize to repo-relative POSIX path; reject traversal and absolutes."""
    raw = (path or "").strip().replace("\\", "/")
    if not raw:
        raise PatchPathError("empty path")
    if raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        raise PatchPathError(f"absolute path not allowed: {path!r}")
    if ".." in PurePosixPath(raw).parts:
        raise PatchPathError(f"path traversal not allowed: {path!r}")
    normalized = PurePosixPath(raw).as_posix()
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def is_protected_patch_path(path: str) -> bool:
    normalized = normalize_repo_relative_path(path)
    for prefix in PROTECTED_PREFIXES:
        if normalized == prefix.rstrip("/") or normalized.startswith(prefix):
            return True
    return False


def normalize_allowed_files(allowed_files: list[str]) -> set[str]:
    return {normalize_repo_relative_path(p) for p in allowed_files if p.strip()}


def validate_allowed_patch_path(path: str, allowed_files: list[str]) -> str:
    """Return normalized path if allowed; raise PatchPathError otherwise."""
    normalized = normalize_repo_relative_path(path)
    if is_protected_patch_path(normalized):
        raise PatchPathError(f"protected path not allowed: {normalized!r}")
    allowed = normalize_allowed_files(allowed_files)
    if normalized not in allowed:
        raise PatchPathError(f"path not in allowed_files: {normalized!r}")
    return normalized
