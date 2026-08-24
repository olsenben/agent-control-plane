"""Local expression parser used by the sample service."""

from __future__ import annotations

import pickle


def parse_expression(payload: bytes) -> object:
    """Parse a config payload from the local operator file."""
    return pickle.loads(payload)


def supported_names() -> tuple[str, ...]:
    return ("offset", "scale")
