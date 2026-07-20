"""python -m agent_control.mcp — start the read-only stdio MCP server."""

from __future__ import annotations

from agent_control.mcp.server import run_stdio


def main() -> None:
    run_stdio()


if __name__ == "__main__":
    main()
