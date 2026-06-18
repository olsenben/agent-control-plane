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


def list_related_adrs(adr_dir: Path, adr_ids: list[str]) -> list[dict[str, Any]]:
    """Return adr_fact.v1 entries matching requested ADR ids."""
    if not adr_ids:
        return []
    wanted = {a.lower() for a in adr_ids}
    facts = compile_adrs(adr_dir)
    matched: list[dict[str, Any]] = []
    for fact in facts:
        adr_id = str(fact.get("adr_id", ""))
        if adr_id.lower() in wanted or adr_id.replace("_", "-").lower() in wanted:
            matched.append(fact)
            continue
        for token in wanted:
            if token in adr_id.lower() or token in str(fact.get("title", "")).lower():
                matched.append(fact)
                break
    return matched
