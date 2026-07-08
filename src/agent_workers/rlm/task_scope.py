"""Extract explicit file scope from natural-language task text (Slice 6D.1)."""

from __future__ import annotations

import json
import re

_PSEUDO_SOURCES = frozenset(
    {"gitea_issue", "graph_blast_radius", "memory_retrieval", "prior_memory"}
)

_FILES_JSON_RE = re.compile(
    r'files\s*(?:must\s+be|:)\s*(\[[^\]]+\])',
    re.IGNORECASE,
)
_UPDATE_FILE_RE = re.compile(
    r"\b(?:update|edit|modify|append(?:\s+one\s+line)?\s+(?:to|in)?)\s+([A-Za-z0-9_./-]+\.(?:md|py|yml|yaml|json|txt|toml))\b",
    re.IGNORECASE,
)


def extract_explicit_files_from_task(task: str) -> list[str]:
    """Parse explicit repo-relative paths from plan/fix task commands."""
    if not task:
        return []
    found: list[str] = []
    match = _FILES_JSON_RE.search(task)
    if match:
        try:
            parsed = json.loads(match.group(1))
            if isinstance(parsed, list):
                found.extend(str(p).strip() for p in parsed if str(p).strip())
        except json.JSONDecodeError:
            pass
    for m in _UPDATE_FILE_RE.finditer(task):
        found.append(m.group(1).strip())
    deduped: list[str] = []
    seen: set[str] = set()
    for path in found:
        norm = path.replace("\\", "/").lstrip("./")
        if not norm or norm in _PSEUDO_SOURCES or norm in seen:
            continue
        seen.add(norm)
        deduped.append(norm)
    return deduped


def pick_plan_step_files(task: str, sources: list[str]) -> list[str]:
    explicit = extract_explicit_files_from_task(task)
    if explicit:
        return explicit[:1]
    for src in sources:
        if src not in _PSEUDO_SOURCES:
            return [src]
    return sources[:1] if sources else ["README.md"]
