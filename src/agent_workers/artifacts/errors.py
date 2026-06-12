"""Write error.json for failed runs."""

from __future__ import annotations

from pathlib import Path

from agent_shared.models.runs import AgentError
from agent_workers.artifacts.writer import write_json


def write_error(path: Path, error: AgentError) -> None:
    write_json(path, error.model_dump(mode="json"))
