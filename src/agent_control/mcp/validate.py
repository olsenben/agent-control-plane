"""JSON Schema validation for MCP tool outputs."""

from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator

MCP_TOOL_RESULT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "mcp_tool_result.v1",
    "type": "object",
    "required": ["schema", "ok", "tool"],
    "additionalProperties": True,
    "properties": {
        "schema": {"const": "mcp_tool_result.v1"},
        "ok": {"type": "boolean"},
        "tool": {"type": "string"},
        "repo": {"type": "string"},
        "data": {"type": "object"},
        "error": {"type": "string"},
        "evidence_refs": {"type": "array", "items": {"type": "string"}},
        "_truncated": {"type": "boolean"},
        "preview": {"type": "string"},
    },
}

_VALIDATOR = Draft202012Validator(MCP_TOOL_RESULT_SCHEMA)


def validate_tool_result(payload: dict[str, Any]) -> dict[str, Any]:
    """Raise jsonschema.ValidationError if payload is not a valid tool result."""
    _VALIDATOR.validate(payload)
    return payload


def envelope(
    *,
    tool: str,
    ok: bool,
    data: dict[str, Any] | None = None,
    error: str = "",
    repo: str | None = None,
    evidence_refs: list[str] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema": "mcp_tool_result.v1",
        "ok": ok,
        "tool": tool,
        "data": data or {},
        "evidence_refs": list(evidence_refs or []),
    }
    if repo is not None:
        body["repo"] = repo
    if error:
        body["error"] = error
    return validate_tool_result(body)
