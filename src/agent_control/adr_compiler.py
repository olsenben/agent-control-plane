"""ADR Markdown compiler (stub)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def parse_adr_front_matter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"missing front matter: {path}")
    _, fm, _ = text.split("---", 2)
    return yaml.safe_load(fm) or {}


def compile_adrs(adr_dir: Path) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    if not adr_dir.is_dir():
        return facts
    for path in sorted(adr_dir.glob("*.md")):
        meta = parse_adr_front_matter(path)
        if meta.get("status") in ("superseded", "withdrawn", "deprecated"):
            continue
        facts.append(
            {
                "schema": "adr_fact.v1",
                "adr_id": meta.get("id", path.stem),
                "title": meta.get("title", path.stem),
                "state": "active",
                "source_path": str(path),
            }
        )
    return facts
