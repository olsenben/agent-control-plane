"""Filesystem-durable inbound event dedup. First processed result wins."""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

DUPLICATE = "DUPLICATE"
PROCESSED = "PROCESSED"

INBOUND_EVENT_TYPES = (
    "webhook",
    "proposal",
    "evidence",
    "admission",
    "broker",
    "ci",
)

_LOCK = threading.Lock()


def inbound_dir(state_root: Path) -> Path:
    return Path(state_root) / "transaction" / "inbound"


def inbound_path(state_root: Path, event_id: str) -> Path:
    return inbound_dir(state_root) / f"{_safe_event_id(event_id)}.json"


def _safe_event_id(event_id: str) -> str:
    text = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in str(event_id))
    return (text[:160] if text else "unknown")


def _load_record(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def duplicate(state_root: Path, event_id: str) -> dict[str, Any] | None:
    """Return DUPLICATE with the original result, or None if unseen."""
    record = _load_record(inbound_path(state_root, event_id))
    if record is None:
        return None
    return {
        "status": DUPLICATE,
        "event_id": str(record.get("event_id") or event_id),
        "event_type": record.get("event_type"),
        "result": record.get("result"),
        "original": record.get("result"),
    }


def process_inbound(
    state_root: Path,
    event_type: str,
    event_id: str,
    handler: Callable[[], Any],
) -> dict[str, Any]:
    """Invoke handler at most once per incoming_event_id. Duplicates replay the first result."""
    path = inbound_path(state_root, event_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        existing = duplicate(state_root, event_id)
        if existing is not None:
            return existing
        result = handler()
        payload = {
            "event_id": str(event_id),
            "event_type": str(event_type),
            "status": PROCESSED,
            "result": result,
        }
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, path)
        return {
            "status": PROCESSED,
            "event_id": str(event_id),
            "event_type": str(event_type),
            "result": result,
        }
