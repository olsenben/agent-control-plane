"""Canonical session terminal reason taxonomy (Slice 5.4b)."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Literal

SessionTerminalStatus = Literal["finished", "failed", "blocked"]


class SessionTerminalError(ValueError):
    """Invalid terminal status/reason combination."""


class SessionTerminalReason(StrEnum):
    # finished
    INGEST_COMPLETED = "ingest_completed"
    PUBLISH_SUCCEEDED = "publish_succeeded"
    REPAIR_PUBLISH_SUCCEEDED = "repair_publish_succeeded"
    # failed
    ENQUEUE_FAILED = "enqueue_failed"
    WORKER_FAILED = "worker_failed"
    PUBLISH_FAILED = "publish_failed"
    SESSION_FAILED = "session_failed"
    # blocked
    POLICY_DENIED = "policy_denied"
    HUMAN_APPROVAL_REQUIRED = "human_approval_required"
    SANDBOX_UNAVAILABLE = "sandbox_unavailable"
    SESSION_BLOCKED = "session_blocked"
    # reserved (5.5 / 5.6)
    VERIFICATION_MISSING = "verification_missing"
    CONTEXT_OVERFLOW = "context_overflow"


ALLOWED_REASONS_BY_STATUS: dict[SessionTerminalStatus, frozenset[SessionTerminalReason]] = {
    "finished": frozenset(
        {
            SessionTerminalReason.INGEST_COMPLETED,
            SessionTerminalReason.PUBLISH_SUCCEEDED,
            SessionTerminalReason.REPAIR_PUBLISH_SUCCEEDED,
        }
    ),
    "failed": frozenset(
        {
            SessionTerminalReason.ENQUEUE_FAILED,
            SessionTerminalReason.WORKER_FAILED,
            SessionTerminalReason.PUBLISH_FAILED,
            SessionTerminalReason.SESSION_FAILED,
        }
    ),
    "blocked": frozenset(
        {
            SessionTerminalReason.POLICY_DENIED,
            SessionTerminalReason.HUMAN_APPROVAL_REQUIRED,
            SessionTerminalReason.SANDBOX_UNAVAILABLE,
            SessionTerminalReason.SESSION_BLOCKED,
            SessionTerminalReason.VERIFICATION_MISSING,
            SessionTerminalReason.CONTEXT_OVERFLOW,
        }
    ),
}

_SANDBOX_PREFIXES = (
    "sandbox_",
    "workspace_quarantined",
    "sandbox_unavailable",
)

_POLICY_ATTESTATION_CODES = frozenset(
    {
        "effective_command_policy_hash_mismatch",
        "protected_path",
        "branch_policy",
        "protected_branch",
        "repository_not_allowlisted",
        "repair_publish_disabled",
        "repair_allowlist_empty",
    }
)


def _coerce_reason(reason: SessionTerminalReason | str) -> SessionTerminalReason:
    if isinstance(reason, SessionTerminalReason):
        return reason
    try:
        return SessionTerminalReason(str(reason))
    except ValueError:
        raise SessionTerminalError(f"unknown terminal reason code: {reason!r}") from None


def format_terminal_reason_detail(
    message: str | None = None,
    *,
    domain_reasons: list[str] | None = None,
) -> str | None:
    if not message and not domain_reasons:
        return None
    payload: dict[str, object] = {}
    if message:
        payload["message"] = message
    if domain_reasons:
        payload["domain_reasons"] = list(domain_reasons)
    return json.dumps(payload, sort_keys=True)


def normalize_terminal(
    status: SessionTerminalStatus,
    reason: SessionTerminalReason | str,
    *,
    domain_reasons: list[str] | None = None,
    message: str | None = None,
) -> tuple[SessionTerminalStatus, SessionTerminalReason, str | None]:
    """Validate status/reason combo; build structured terminal_reason detail."""
    coerced = _coerce_reason(reason)
    allowed = ALLOWED_REASONS_BY_STATUS.get(status)
    if allowed is None or coerced not in allowed:
        raise SessionTerminalError(
            f"reason {coerced.value!r} not allowed for terminal status {status!r}"
        )
    detail = format_terminal_reason_detail(message, domain_reasons=domain_reasons)
    return status, coerced, detail


def classify_unsuccessful_terminal(
    *,
    domain_reasons: list[str] | None = None,
    policy_decision: str | None = None,
    context: str = "",
) -> tuple[Literal["failed", "blocked"], SessionTerminalReason]:
    """Map domain signals to blocked vs failed + canonical reason (never success codes)."""
    reasons = [str(r) for r in (domain_reasons or []) if r]
    lowered = [r.lower() for r in reasons]

    if policy_decision == "deny":
        return "blocked", SessionTerminalReason.POLICY_DENIED

    for code in lowered:
        if code.startswith(_SANDBOX_PREFIXES) or any(
            code.startswith(p) for p in _SANDBOX_PREFIXES
        ):
            return "blocked", SessionTerminalReason.SANDBOX_UNAVAILABLE
        if code in _POLICY_ATTESTATION_CODES or code.endswith("_not_allowlisted"):
            return "blocked", SessionTerminalReason.POLICY_DENIED
        if "human_approval" in code or code == "approval_missing":
            return "blocked", SessionTerminalReason.HUMAN_APPROVAL_REQUIRED

    if context == "broker_safety_policy":
        return "blocked", SessionTerminalReason.POLICY_DENIED

    if context == "broker_operational":
        return "failed", SessionTerminalReason.PUBLISH_FAILED

    if reasons:
        return "failed", SessionTerminalReason.SESSION_FAILED
    return "failed", SessionTerminalReason.WORKER_FAILED


def map_fix_evaluation_to_block_reason(
    *,
    evaluation_reason: str | None,
    empty_allowed_files: bool = False,
) -> SessionTerminalReason:
    """Map FixEvaluation.blocked paths to canonical block reasons."""
    if empty_allowed_files:
        return SessionTerminalReason.POLICY_DENIED
    text = (evaluation_reason or "").lower()
    if "no approval" in text or "use /agent approve" in text:
        return SessionTerminalReason.HUMAN_APPROVAL_REQUIRED
    return SessionTerminalReason.POLICY_DENIED


def classify_broker_reject(
    *,
    broker_reason: str,
    detail: list[str] | str | None = None,
) -> tuple[SessionTerminalStatus, SessionTerminalReason]:
    """Explicit broker reject → terminal status + canonical reason."""
    domain: list[str] = []
    if isinstance(detail, list):
        domain = [str(d) for d in detail]
    elif detail:
        domain = [str(detail)]

    reason = broker_reason.lower()

    if reason == "attestation_gate":
        return "blocked", SessionTerminalReason.SANDBOX_UNAVAILABLE
    if reason in ("approval_missing", "approval_unavailable", "no_trusted_sha"):
        return "blocked", SessionTerminalReason.POLICY_DENIED
    if reason in ("missing_binding",):
        return "failed", SessionTerminalReason.PUBLISH_FAILED
    if reason == "bundle_invalid":
        return "failed", SessionTerminalReason.PUBLISH_FAILED
    if reason == "stale_base":
        return "failed", SessionTerminalReason.PUBLISH_FAILED
    if reason in ("base_sha_mismatch",):
        return "failed", SessionTerminalReason.PUBLISH_FAILED
    if reason in ("push_failed", "claim_failed", "pr_open_failed", "api_unavailable"):
        return "failed", SessionTerminalReason.PUBLISH_FAILED

    # Policy-style repair / repository gates
    if reason in ("repository_not_allowlisted", "repair_publish_disabled"):
        return "blocked", SessionTerminalReason.POLICY_DENIED
    if domain and any("not_allowlisted" in d for d in domain):
        return "blocked", SessionTerminalReason.POLICY_DENIED

    # ValidationError reasons from validate.py
    if reason in (
        "scope_violation",
        "closed_world_violation",
        "policy_denied",
        "diff_gate",
    ):
        return "blocked", SessionTerminalReason.POLICY_DENIED

    status, canonical = classify_unsuccessful_terminal(
        domain_reasons=domain,
        context="broker_operational" if reason.endswith("_failed") else "broker_safety_policy",
    )
    return status, canonical
