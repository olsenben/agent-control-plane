"""Secret redaction before writing logs or comments."""

from __future__ import annotations

import os
import re
from typing import Any

_ENV_KEY = re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*\S+")
_SSH_KEY = re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----[\s\S]+?-----END [A-Z ]+PRIVATE KEY-----")
_BEARER = re.compile(r"(?i)bearer\s+[a-z0-9\-_.~+/]+=*")
_GENERIC_TOKEN = re.compile(r"(?i)(glpat-|ghp_|gho_|sk-[a-z0-9]{10,})")


class SecretRedactor:
    def __init__(self, known_secrets: list[str] | None = None) -> None:
        secrets = list(known_secrets or [])
        for name in ("GITEA_AGENT_TOKEN", "GITEA_BOT_TOKEN", "GITEA_WEBHOOK_SECRET"):
            val = os.environ.get(name, "")
            if val:
                secrets.append(val)
        self.known_secrets = [s for s in secrets if s]
        self.rules_loaded = 4 + len(self.known_secrets)

    def redact_text(self, text: str) -> tuple[str, int]:
        if not text:
            return text, 0
        count = 0
        result = text
        for secret in self.known_secrets:
            if secret in result:
                result = result.replace(secret, "[REDACTED]")
                count += 1
        for pattern in (_SSH_KEY, _BEARER, _GENERIC_TOKEN, _ENV_KEY):
            new_result, n = pattern.subn("[REDACTED]", result)
            result = new_result
            count += n
        return result, count

    def redact_dict(self, data: dict[str, Any]) -> tuple[dict[str, Any], int]:
        total = 0
        out: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, str):
                cleaned, n = self.redact_text(value)
                out[key] = cleaned
                total += n
            elif isinstance(value, dict):
                cleaned, n = self.redact_dict(value)
                out[key] = cleaned
                total += n
            else:
                out[key] = value
        return out, total
