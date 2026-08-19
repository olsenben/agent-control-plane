"""Ripgrep subprocess helper for lexical evidence.

Availability is explicit: a missing binary is not a zero-hit search.
This module does not mutate a workspace git HEAD.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

RG_TIMEOUT_SECONDS = 5.0
RG_MAX_COUNT_PER_FILE = 3
RG_MAX_FILESIZE = "1M"


class RipgrepError(RuntimeError):
    """rg was present but the search could not be completed."""


@dataclass(frozen=True)
class RipgrepMatch:
    path: str
    line_number: int
    line_text: str


def ripgrep_available() -> bool:
    return shutil.which("rg") is not None


def search_workspace(workspace: Path, terms: tuple[str, ...]) -> list[RipgrepMatch]:
    """Return content matches for ``terms`` under ``workspace``.

    Caller must have confirmed ``ripgrep_available()``. Empty ``terms`` yields
    no subprocess. Exit code 1 (no matches) is an empty list. Timeout, OSError,
    or rg exit 2 raise ``RipgrepError``.
    """
    if not terms:
        return []
    root = workspace.resolve()
    if not root.is_dir():
        return []
    argv = [
        "rg",
        "--json",
        "--sort",
        "path",
        "--fixed-strings",
        "--ignore-case",
        "--max-count",
        str(RG_MAX_COUNT_PER_FILE),
        "--max-filesize",
        RG_MAX_FILESIZE,
        "--glob",
        "!.git",
    ]
    for term in terms:
        argv.extend(["-e", term])
    argv.append(".")
    try:
        proc = subprocess.run(
            argv,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=RG_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RipgrepError("rg timed out") from exc
    except OSError as exc:
        raise RipgrepError("rg could not be executed") from exc
    if proc.returncode not in (0, 1):
        detail = (proc.stderr or "").strip() or f"rg exit {proc.returncode}"
        raise RipgrepError(detail)
    return _parse_json_matches(root, proc.stdout)


def _parse_json_matches(root: Path, stdout: str) -> list[RipgrepMatch]:
    hits: list[RipgrepMatch] = []
    for raw_line in stdout.splitlines():
        if not raw_line.strip():
            continue
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if payload.get("type") != "match":
            continue
        data = payload.get("data") or {}
        path_obj = data.get("path") or {}
        raw_path = path_obj.get("text") if isinstance(path_obj, dict) else None
        if not isinstance(raw_path, str) or not raw_path:
            continue
        rel = _rel_posix(root, raw_path)
        if rel is None:
            continue
        line_number = data.get("line_number")
        if not isinstance(line_number, int) or line_number < 1:
            continue
        lines_obj = data.get("lines") or {}
        line_text = lines_obj.get("text") if isinstance(lines_obj, dict) else ""
        if not isinstance(line_text, str):
            line_text = ""
        hits.append(
            RipgrepMatch(path=rel, line_number=line_number, line_text=line_text.rstrip("\n"))
        )
    return hits


def _rel_posix(root: Path, raw_path: str) -> str | None:
    path = Path(raw_path)
    try:
        resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return None
