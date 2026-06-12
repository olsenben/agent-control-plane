"""Tool registry with policy enforcement and ExecutionTool dispatch skeleton."""

from __future__ import annotations

from typing import Any, Callable

from agent_shared.constants import SessionEventType
from agent_workers.tools.base import ExecutionTool


class ToolRegistry:
    """Policy-checked tool dispatch. External ExecutionTools are disabled in Spike 0."""

    def __init__(
        self,
        allowed: set[str],
        policy: dict[str, Any],
        emit_reject: Callable[[str, str], None],
        external_tools: dict[str, ExecutionTool] | None = None,
    ) -> None:
        self.allowed = allowed
        self.policy = policy
        self.emit_reject = emit_reject
        self.external_tools: dict[str, ExecutionTool] = external_tools or {}
        self._internal_tools: dict[str, Callable[..., Any]] = {
            "read_repo": self._read_repo,
            "search_code": self._search_code,
            "read_context": self._read_context,
        }

    def execute(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        if tool not in self.allowed:
            self.emit_reject(tool, "unknown_tool")
            raise PermissionError(f"unknown tool: {tool}")
        if tool in self.external_tools:
            self.emit_reject(tool, "external_tool_disabled")
            raise PermissionError(f"external tool not enabled: {tool}")
        if tool not in self._internal_tools:
            self.emit_reject(tool, "not_implemented")
            raise PermissionError(f"tool not registered: {tool}")
        return self._internal_tools[tool](**args)

    def validate_model_tool_call(self, tool: str, args: dict[str, Any]) -> bool:
        if tool not in self.allowed:
            self.emit_reject(tool, "policy_denied")
            return False
        path = args.get("path", "")
        for pattern in self.policy.get("protected_paths", []):
            if pattern.rstrip("*") in str(path):
                self.emit_reject(tool, "protected_path")
                return False
        return True

    def _read_repo(self, path: str = ".", **_: Any) -> dict[str, Any]:
        return {"path": path, "status": "stub_read"}

    def _search_code(self, query: str = "", **_: Any) -> dict[str, Any]:
        return {"query": query, "matches": []}

    def _read_context(self, name: str = "", **_: Any) -> dict[str, Any]:
        return {"name": name, "status": "stub_context"}


def make_registry(effective_policy: dict[str, Any], session_writer) -> ToolRegistry:
    allowed = set(effective_policy.get("allowed_tools") or [])

    def emit_reject(tool: str, reason: str) -> None:
        session_writer.emit(
            SessionEventType.TOOL_CALL_REJECTED,
            tool=tool,
            reason=reason,
        )

    return ToolRegistry(allowed, effective_policy, emit_reject)
