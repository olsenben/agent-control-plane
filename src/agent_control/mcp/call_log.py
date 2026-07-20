"""Tool-call audit log for the read-only MCP server."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("agent_control.mcp")


def log_tool_call(
    *,
    tool: str,
    args: dict[str, Any],
    ok: bool,
    error: str = "",
    log_path: Path | None = None,
) -> None:
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "tool": tool,
        "ok": ok,
        "arg_keys": sorted(args.keys()),
        "error": error or None,
    }
    line = json.dumps(record, default=str)
    logger.info("mcp_tool_call %s", line)
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
