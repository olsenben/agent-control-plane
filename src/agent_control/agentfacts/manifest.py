"""Build / load AgentFacts-lite manifests from agent-card sources."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from agent_control.agentfacts.sign import attach_integrity
from agent_control.agentfacts.sync import extract_human_card

DEFAULT_MANIFEST_NAME = "agent-facts.json"
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "agent_facts.schema.json"

_VALIDATOR: Draft202012Validator | None = None


def _validator() -> Draft202012Validator:
    global _VALIDATOR
    if _VALIDATOR is None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        _VALIDATOR = Draft202012Validator(schema)
    return _VALIDATOR


def validate_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    _validator().validate(manifest)
    return manifest


def repo_paths(repo_root: Path) -> tuple[Path, Path, Path]:
    root = repo_root.resolve()
    return (
        root / "docs" / "AGENT_CARD.md",
        root / "agent-card.json",
        root / DEFAULT_MANIFEST_NAME,
    )


def build_manifest(
    *,
    agent_card_md: Path,
    agent_card_json: Path,
    signing_secret: str | None = None,
    signed_by: str = "CT103",
) -> dict[str, Any]:
    """Derive AgentFacts-lite from human + machine cards and attach integrity."""
    md_bytes = agent_card_md.read_bytes()
    json_bytes = agent_card_json.read_bytes()
    card = json.loads(json_bytes.decode("utf-8"))
    human = extract_human_card(md_bytes.decode("utf-8"))

    commands = []
    for c in card.get("commands") or []:
        commands.append(
            {
                "name": c["name"],
                "risk_class": int(c["risk_class"]),
                "human_approval_required": bool(c.get("human_approval_required", False)),
                "repo_access": c.get("repo_access"),
                "memory_writeback": c.get("memory_writeback"),
            }
        )

    raw: dict[str, Any] = {
        "schema_version": "agent_facts.v1",
        "name": card.get("name") or human["name"],
        "signed_by": signed_by,
        "signed_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "capabilities": {
            "commands": commands,
            "blocked_commands": list(card.get("blocked_commands") or []),
            "hosts": {
                "governance": card.get("governance_host", "CT103"),
                "execution": card.get("execution_host", "CT104"),
                "ci_truth": card.get("ci_truth_host", "CT102"),
            },
            "write_boundaries": {
                "publish_broker_only": True,
                "ct104_gitea_write": False,
                "main_push_allowed": False,
            },
        },
        "limitations": list(human["limitations"]),
        "documentation": dict(card.get("documentation") or {}),
    }
    signed = attach_integrity(
        raw,
        agent_card_md_bytes=md_bytes,
        agent_card_json_bytes=json_bytes,
        signing_secret=signing_secret,
    )
    return validate_manifest(signed)


def load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("agent-facts manifest must be a JSON object")
    return validate_manifest(data)


def write_manifest(path: Path, manifest: dict[str, Any]) -> Path:
    validate_manifest(manifest)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
