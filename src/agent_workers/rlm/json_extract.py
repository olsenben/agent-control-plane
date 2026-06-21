"""Canonical JSON extraction from model text output."""

from __future__ import annotations

import json
import re
from typing import Any


class JsonExtractError(ValueError):
    """Raised when no valid JSON object can be extracted from model output."""


def extract_json_blob(raw: str) -> dict[str, Any]:
    text = raw.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if fence_match:
        return json.loads(fence_match.group(1))
    start = text.find("{")
    if start < 0:
        raise JsonExtractError("No JSON object found in model output")
    depth = 0
    for idx in range(start, len(text)):
        ch = text[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : idx + 1])
    raise JsonExtractError("Unbalanced JSON object in model output")
