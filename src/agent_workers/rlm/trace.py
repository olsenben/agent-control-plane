"""RLM trace append helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def append_trace_event(artifact_dir: str | None, event: dict[str, Any]) -> None:
    if not artifact_dir:
        return
    path = Path(artifact_dir) / "rlm_trace.jsonl"
    payload = {"ts": datetime.now(timezone.utc).isoformat(), **event}
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
