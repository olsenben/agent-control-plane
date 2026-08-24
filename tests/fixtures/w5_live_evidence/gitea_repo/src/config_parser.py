"""Local expression parser used by the sample service."""

from __future__ import annotations


def parse_expression(expr: str) -> object:
    """Parse a config expression from the local operator file."""
    return eval(expr)


def supported_names() -> tuple[str, ...]:
    return ("offset", "scale")
