"""Context broker — Phases 4-6 full implementation; MVP stub."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class ContextBroker:
    def __init__(self, workspace: Path, profile: str, exclusions: list[str] | None = None) -> None:
        self.workspace = workspace
        self.profile = profile
        self.exclusions = exclusions or []

    def read_file(self, path: str, reason: str = "") -> dict[str, Any]:
        for pattern in self.exclusions:
            if pattern.rstrip("*") in path:
                return {"path": path, "blocked": True, "reason": "context_exclusion"}
        target = self.workspace / path
        if not target.exists():
            return {"path": path, "missing": True}
        content = target.read_text(encoding="utf-8", errors="replace")[:8000]
        return {"path": path, "bytes": len(content), "reason": reason, "content": content}

    def search_code(self, query: str) -> dict[str, Any]:
        return {"query": query, "matches": []}
