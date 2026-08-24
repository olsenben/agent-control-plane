"""Local expression parser used by the sample service."""

from __future__ import annotations


def parse_expression(raw_expr: str) -> object:
    """Parse a config expression from the local operator file."""
    stripped = raw_expr.strip()
    return eval(stripped)


def supported_names() -> tuple[str, ...]:
    return ("offset", "scale")
