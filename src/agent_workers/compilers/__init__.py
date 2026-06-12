"""Context compiler stubs — Phases 4-6."""

from __future__ import annotations

from pathlib import Path


def compile_adr_index(repo: Path, output: Path) -> dict:
    return {"status": "stub", "output": str(output)}


def compile_symbol_index(repo: Path, output: Path) -> dict:
    return {"status": "stub", "output": str(output)}
