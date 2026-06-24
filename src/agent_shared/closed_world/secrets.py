"""Secret pattern detection for diff gate (added lines only)."""

from __future__ import annotations

import re

_AWS_ACCESS_KEY = re.compile(r"AWS_ACCESS_KEY_ID\s*=\s*\S+")
_AWS_SECRET_KEY = re.compile(r"AWS_SECRET_ACCESS_KEY\s*=\s*\S+")
_OPENAI_KEY = re.compile(r"OPENAI_API_KEY\s*=\s*\S+")
_GITEA_TOKEN = re.compile(r"GITEA_AGENT_TOKEN\s*=\s*\S+")
_PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----")
_BEARER = re.compile(r"(?i)Authorization:\s*Bearer\s+\S+")
_ENV_SECRET = re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*\S+")

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (_AWS_ACCESS_KEY, "AWS_ACCESS_KEY_ID assignment"),
    (_AWS_SECRET_KEY, "AWS_SECRET_ACCESS_KEY assignment"),
    (_OPENAI_KEY, "OPENAI_API_KEY assignment"),
    (_GITEA_TOKEN, "GITEA_AGENT_TOKEN assignment"),
    (_PRIVATE_KEY, "private key header"),
    (_BEARER, "Authorization Bearer token"),
    (_ENV_SECRET, "credential assignment"),
)


def scan_added_lines_for_secrets(lines: list[str]) -> list[str]:
    """Return human-readable reasons for secret matches in added lines."""
    hits: list[str] = []
    for line in lines:
        for pattern, label in _PATTERNS:
            if pattern.search(line):
                hits.append(label)
                break
    return hits
