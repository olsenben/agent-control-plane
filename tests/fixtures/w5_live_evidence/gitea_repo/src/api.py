"""Public API surface for the sample service."""

from __future__ import annotations

from .labels import format_label


def public_greeting(name: str) -> str:
    return f"Hello, {format_label(name)}"
