"""Verification sandbox — Step F implementation."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def run_verification_sandbox(patch_path: Path, workspace: Path, commands: list[str]) -> dict[str, Any]:
    return {
        "schema_version": "verification_result.v1",
        "status": "not_implemented",
        "passed": False,
        "message": "Verification sandbox not enabled until Step F",
        "commands": [],
        "sandbox": {"network": False, "secrets_mounted": False, "destroyed": True},
    }
