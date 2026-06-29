"""Redacted artifact writes for Slice 6D publish paths."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_workers.security.redactor import SecretRedactor


def redact_publish_payload(data: dict[str, Any]) -> tuple[dict[str, Any], int]:
    return SecretRedactor().redact_dict(data)


def write_redacted_json(path: Path, data: dict[str, Any]) -> int:
    cleaned, count = redact_publish_payload(data)
    path.write_text(json.dumps(cleaned, indent=2), encoding="utf-8")
    return count


def redact_publish_text(text: str) -> str:
    cleaned, _ = SecretRedactor().redact_text(text)
    return cleaned
