"""Minimal stdio MCP server (JSON-RPC, newline-delimited) — read-only tools only."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, TextIO

from agent_control.mcp.registry import FORBIDDEN_TOOLS, invoke_tool, list_tools

logger = logging.getLogger("agent_control.mcp.server")

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "agent-control-plane-readonly", "version": "0.1.0"}


class ReadonlyMcpServer:
    """Line-delimited JSON-RPC MCP server over stdin/stdout."""

    def __init__(self, *, log_path: Path | None = None) -> None:
        self.log_path = log_path
        self._initialized = False

    def handle_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
        method = message.get("method")
        msg_id = message.get("id")
        params = message.get("params") or {}

        # Notifications have no id and expect no response.
        if msg_id is None and method and not str(method).startswith("tools/"):
            if method == "notifications/initialized":
                self._initialized = True
            return None

        if method == "initialize":
            return self._result(
                msg_id,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": SERVER_INFO,
                    "instructions": (
                        "Read-only graph/memory/state projections. "
                        "No write, shell, git push, ADR mutation, or state mutation tools."
                    ),
                },
            )

        if method == "ping":
            return self._result(msg_id, {})

        if method == "tools/list":
            return self._result(msg_id, {"tools": list_tools()})

        if method == "tools/call":
            name = str(params.get("name") or "")
            arguments = params.get("arguments") or {}
            if not isinstance(arguments, dict):
                arguments = {}
            if name in FORBIDDEN_TOOLS:
                return self._result(
                    msg_id,
                    {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(
                                    {
                                        "schema": "mcp_tool_result.v1",
                                        "ok": False,
                                        "tool": name,
                                        "error": "forbidden_write_tool",
                                    }
                                ),
                            }
                        ],
                        "isError": True,
                    },
                )
            result = invoke_tool(name, arguments, log_path=self.log_path)
            text = json.dumps(result, default=str)
            return self._result(
                msg_id,
                {
                    "content": [{"type": "text", "text": text}],
                    "structuredContent": result,
                    "isError": not bool(result.get("ok")),
                },
            )

        if method == "resources/list":
            return self._result(msg_id, {"resources": []})

        if method == "prompts/list":
            return self._result(msg_id, {"prompts": []})

        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    @staticmethod
    def _result(msg_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    def serve(self, stdin: TextIO | None = None, stdout: TextIO | None = None) -> None:
        inp = stdin or sys.stdin
        out = stdout or sys.stdout
        for line in inp:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                err = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"},
                }
                out.write(json.dumps(err) + "\n")
                out.flush()
                continue
            if not isinstance(message, dict):
                continue
            response = self.handle_message(message)
            if response is not None:
                out.write(json.dumps(response, default=str) + "\n")
                out.flush()


def run_stdio(*, log_path: Path | None = None) -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    ReadonlyMcpServer(log_path=log_path).serve()
