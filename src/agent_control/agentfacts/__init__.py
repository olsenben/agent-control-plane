"""AgentFacts-lite — signed capability / limitation manifests (V5 T01)."""

from __future__ import annotations

from agent_control.agentfacts.check import CheckResult, verify_agentfacts
from agent_control.agentfacts.manifest import (
    DEFAULT_MANIFEST_NAME,
    build_manifest,
    load_manifest,
    write_manifest,
)
from agent_control.agentfacts.sign import attach_integrity, verify_integrity
from agent_control.agentfacts.sync import SyncResult, check_card_sync

__all__ = [
    "DEFAULT_MANIFEST_NAME",
    "CheckResult",
    "SyncResult",
    "attach_integrity",
    "build_manifest",
    "check_card_sync",
    "load_manifest",
    "verify_agentfacts",
    "verify_integrity",
    "write_manifest",
]
