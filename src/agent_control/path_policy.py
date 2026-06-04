"""Path glob helpers using stdlib fnmatch."""

from __future__ import annotations

from fnmatch import fnmatch


def matches_any(path: str, patterns: list[str]) -> bool:
    """Return True if path matches any glob pattern."""
    return any(fnmatch(path, pattern) for pattern in patterns)


def is_denied(path: str, denied: list[str]) -> bool:
    return matches_any(path, denied)
