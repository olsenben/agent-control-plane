"""Typed ACI tools (stubs)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def list_tree(root: Path, max_depth: int = 3) -> list[str]:
    paths: list[str] = []
    root = root.resolve()
    for path in root.rglob("*"):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            if rel.count("/") <= max_depth:
                paths.append(rel)
    return sorted(paths)[:500]


def read_file(path: Path, max_bytes: int = 20000) -> str:
    data = path.read_bytes()[:max_bytes]
    return data.decode("utf-8", errors="replace")


def run_command(command_id: str, cwd: Path | None = None) -> dict[str, Any]:
    return {"command_id": command_id, "status": "stub", "cwd": str(cwd) if cwd else None}
