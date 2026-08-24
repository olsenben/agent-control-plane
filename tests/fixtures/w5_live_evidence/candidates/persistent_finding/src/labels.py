"""Public display helpers."""

from __future__ import annotations


def format_label(name: str) -> str:
    """Public helper used by callers to normalize a display name."""
    return name.strip().title()
