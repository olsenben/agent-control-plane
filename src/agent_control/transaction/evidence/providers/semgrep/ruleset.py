"""Frozen Semgrep CE version pin and local ruleset snapshot."""

from __future__ import annotations

import hashlib
from pathlib import Path

# Pinned Semgrep Community Edition. Do not float; do not use --config auto.
SEMGREP_VERSION = "1.110.0"
SEMGREP_IMAGE = f"semgrep/semgrep:{SEMGREP_VERSION}"
CASE_SPECIFIC_RULE_ADDED = "NO"
RULESET_FILENAME = "python-security.yaml"


def ruleset_path() -> Path:
    return Path(__file__).resolve().parent / "rules" / RULESET_FILENAME


def resources_ruleset_path() -> Path:
    """Repo-root snapshot used by scanner_ruleset_manifest.json."""
    here = Path(__file__).resolve()
    return here.parents[6] / "resources" / "evidence" / "semgrep" / RULESET_FILENAME


def compute_ruleset_digest(path: Path | None = None) -> str:
    target = path or ruleset_path()
    return hashlib.sha256(target.read_bytes()).hexdigest()


def loaded_rule_ids(path: Path | None = None) -> list[str]:
    import yaml

    payload = yaml.safe_load((path or ruleset_path()).read_text(encoding="utf-8")) or {}
    rules = payload.get("rules") if isinstance(payload, dict) else None
    ids: list[str] = []
    for item in rules or []:
        if isinstance(item, dict) and item.get("id"):
            ids.append(str(item["id"]))
    return ids


RULESET_DIGEST = compute_ruleset_digest()
