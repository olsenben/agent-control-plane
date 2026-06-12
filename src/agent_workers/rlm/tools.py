"""Backward-compatible re-export of ToolRegistry."""

from agent_workers.tools.registry import ToolRegistry, make_registry

__all__ = ["ToolRegistry", "make_registry"]
