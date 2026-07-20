"""Response size bounds for read-only MCP tools."""

from __future__ import annotations

import json
from typing import Any

MAX_LIST_ITEMS = 50
MAX_STRING_CHARS = 4_000
MAX_PAYLOAD_CHARS = 32_000
MAX_FINDINGS = 20
MAX_MEMORY_RECORDS = 10
MAX_ADR_FACTS = 20
MAX_POLICY_CHARS = 16_000


def truncate_str(value: str | None, limit: int = MAX_STRING_CHARS) -> str:
    if not value:
        return ""
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 14)] + "…[truncated]"


def bound_list(items: list[Any], limit: int = MAX_LIST_ITEMS) -> list[Any]:
    return list(items[:limit])


def bound_payload(data: Any, *, max_chars: int = MAX_PAYLOAD_CHARS) -> Any:
    """Ensure JSON serialization stays under max_chars; drop trailing list items if needed."""
    raw = json.dumps(data, default=str)
    if len(raw) <= max_chars:
        return data
    if isinstance(data, dict):
        trimmed = dict(data)
        trimmed["_truncated"] = True
        for key in ("related", "facts", "records", "affected_tests", "path", "findings", "events"):
            if key in trimmed and isinstance(trimmed[key], list):
                while trimmed[key] and len(json.dumps(trimmed, default=str)) > max_chars:
                    trimmed[key] = trimmed[key][:-1]
                if len(json.dumps(trimmed, default=str)) <= max_chars:
                    return trimmed
        # Last resort: keep schema + error note
        return {
            "schema": trimmed.get("schema", "mcp_tool_result.v1"),
            "ok": trimmed.get("ok", True),
            "tool": trimmed.get("tool"),
            "error": "payload_exceeded_bound",
            "_truncated": True,
            "preview": truncate_str(raw, max_chars // 4),
        }
    if isinstance(data, list):
        kept = list(data)
        while kept and len(json.dumps(kept, default=str)) > max_chars:
            kept = kept[:-1]
        return kept
    return truncate_str(str(data), max_chars)
