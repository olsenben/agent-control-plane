"""Canonical input_state_sha and session/correlation ID helpers."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any


def make_session_id() -> str:
    """Opaque session id — always distinct from run-* ids."""
    return f"sess-{uuid.uuid4().hex}"


def make_correlation_id(*, session_id: str, run_id: str) -> str:
    """Stable correlation token for a session+primary-run pair."""
    digest = hashlib.sha256(f"{session_id}:{run_id}".encode("utf-8")).hexdigest()[:24]
    return f"corr-{digest}"


def canonical_input_state(
    *,
    project: str,
    subject_kind: str,
    subject_number: int,
    command_kind: str,
    head_sha: str,
    policy_source_sha: str = "",
) -> dict[str, Any]:
    """Canonical dict for input_state_sha (sorted keys, stable types).

    5.4a scope: dispatch identity only — repo/subject/command + dispatch head SHA
    and optional policy pin. Issue body / comment text are intentionally excluded
    so retries of the same command identity share the digest when those fields match.
    """
    return {
        "command_kind": command_kind,
        "head_sha": head_sha or "",
        "policy_source_sha": policy_source_sha or "",
        "project": project,
        "schema_version": "input_state.v1",
        "subject_kind": subject_kind,
        "subject_number": int(subject_number),
    }


def compute_input_state_sha(
    *,
    project: str,
    subject_kind: str,
    subject_number: int,
    command_kind: str,
    head_sha: str,
    policy_source_sha: str = "",
) -> str:
    """SHA-256 hex of canonical JSON (separators compact, sort_keys=True)."""
    payload = canonical_input_state(
        project=project,
        subject_kind=subject_kind,
        subject_number=subject_number,
        command_kind=command_kind,
        head_sha=head_sha,
        policy_source_sha=policy_source_sha,
    )
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def risk_level_for_command(command_kind: str) -> str:
    """Map command kind to session risk_level label."""
    mapping = {
        "review": "risk_1",
        "plan": "risk_1",
        "fix": "risk_2",
        "repair": "risk_2",
        "inspect": "risk_0",
        "explain": "risk_0",
    }
    return mapping.get(command_kind, "risk_unknown")


def default_risk_tags(command_kind: str) -> list[str]:
    tags = {
        "review": ["command:review", "autonomy:risk_1"],
        "plan": ["command:plan", "autonomy:risk_1"],
        "fix": ["command:fix", "autonomy:risk_2"],
        "repair": ["command:repair", "autonomy:risk_2"],
    }
    return list(tags.get(command_kind, [f"command:{command_kind}"]))
