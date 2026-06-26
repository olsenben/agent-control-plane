"""CT103 ingest job: process a single CT104 inbox file."""

from __future__ import annotations

from pathlib import Path

from agent_control.config import get_settings
from agent_control.results_ingest import ingest_result_file


def process_ingest_inbox_file(state_root: str, inbox_path: str) -> dict:
    settings = get_settings()
    path = Path(inbox_path)
    stored, created = ingest_result_file(Path(state_root), path, settings=settings)
    run_id = path.stem
    if path.name.endswith(".processed"):
        run_id = path.name.replace(".json.processed", "")
    return {
        "run_id": run_id,
        "stored": str(stored),
        "created": created,
        "inbox_path": inbox_path,
    }
