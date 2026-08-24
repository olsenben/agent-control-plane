"""Typed retry classification for transaction-control. Deterministic; no LLM."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from agent_shared.hash_utils import canonical_json_hash

RetryClass = Literal[
    "TRANSIENT",
    "RETRYABLE",
    "PERMANENT",
    "NON_RETRYABLE",
    "AMBIGUOUS_EXTERNAL_EFFECT",
    "RECONCILE_BEFORE_RETRY",
    "TERMINAL_POLICY",
    "MANUAL_INTERVENTION",
]

TRANSIENT: RetryClass = "TRANSIENT"
RETRYABLE: RetryClass = "RETRYABLE"
PERMANENT: RetryClass = "PERMANENT"
NON_RETRYABLE: RetryClass = "NON_RETRYABLE"
AMBIGUOUS_EXTERNAL_EFFECT: RetryClass = "AMBIGUOUS_EXTERNAL_EFFECT"
RECONCILE_BEFORE_RETRY: RetryClass = "RECONCILE_BEFORE_RETRY"
RETRY_SAFE: RetryClass = TRANSIENT
TERMINAL_POLICY: RetryClass = "TERMINAL_POLICY"
MANUAL_INTERVENTION: RetryClass = "MANUAL_INTERVENTION"

RETRYABLE_CLASSES = frozenset({TRANSIENT, RETRYABLE, RETRY_SAFE})
TERMINAL_CLASSES = frozenset({PERMANENT, NON_RETRYABLE, TERMINAL_POLICY, MANUAL_INTERVENTION})
RECONCILE_CLASSES = frozenset({AMBIGUOUS_EXTERNAL_EFFECT, RECONCILE_BEFORE_RETRY})

RETRY_SCOPES = (
    "worker_dispatch",
    "evidence_adapters",
    "gitea_reads",
    "gitea_publish",
    "ci_polling",
)

DEFAULT_RETRY_POLICY: dict[str, dict[str, Any]] = {
    "worker_dispatch": {
        "max_attempts": 3,
        "exhaustion_code": "WORKER_DISPATCH_RETRY_EXHAUSTED",
    },
    "evidence_adapters": {
        "max_attempts": 3,
        "exhaustion_code": "EVIDENCE_ADAPTER_RETRY_EXHAUSTED",
    },
    "gitea_reads": {
        "max_attempts": 5,
        "exhaustion_code": "GITEA_READ_RETRY_EXHAUSTED",
    },
    "gitea_publish": {
        "max_attempts": 2,
        "exhaustion_code": "GITEA_PUBLISH_RETRY_EXHAUSTED",
    },
    "ci_polling": {
        "max_attempts": 10,
        "exhaustion_code": "CI_POLLING_RETRY_EXHAUSTED",
    },
}


@dataclass(frozen=True)
class FailureClassification:
    retry_class: RetryClass
    canonical_class: RetryClass
    requires_reconcile: bool
    retryable: bool
    terminal: bool
    reason: str

    @property
    def code(self) -> RetryClass:
        return self.retry_class


def canonical_retry_class(retry_class: str) -> RetryClass:
    if retry_class in {TRANSIENT, RETRYABLE, RETRY_SAFE}:
        return TRANSIENT
    if retry_class in {PERMANENT, NON_RETRYABLE, TERMINAL_POLICY}:
        return PERMANENT
    if retry_class in {AMBIGUOUS_EXTERNAL_EFFECT, RECONCILE_BEFORE_RETRY}:
        return AMBIGUOUS_EXTERNAL_EFFECT
    if retry_class == MANUAL_INTERVENTION:
        return PERMANENT
    raise ValueError(retry_class)


def classify_exception(
    exc: BaseException,
    *,
    request_sent: bool = False,
    status_code: int | None = None,
) -> FailureClassification:
    """Classify a failure. Timeout-after-send is AMBIGUOUS, never a generic retry."""
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    timeout_like = (
        isinstance(exc, TimeoutError)
        or "timeout" in name
        or "timed out" in message
        or "timeout" in message
    )
    connect_like = (
        "connect" in name
        or "connection refused" in message
        or "name or service not known" in message
        or "temporarily unavailable" in message
    )
    http_status = status_code
    if http_status is None:
        http_status = getattr(exc, "status_code", None)
        if http_status is None:
            response = getattr(exc, "response", None)
            http_status = getattr(response, "status_code", None)

    if request_sent and (timeout_like or "reset" in message or "broken pipe" in message):
        if timeout_like:
            return _class(AMBIGUOUS_EXTERNAL_EFFECT, "timeout_or_drop_after_send")
        return _class(RECONCILE_BEFORE_RETRY, "reset_after_send")
    if http_status in {408, 429} or (isinstance(http_status, int) and 500 <= http_status <= 599):
        return _class(TRANSIENT, f"http_{http_status}")
    if isinstance(http_status, int) and 400 <= http_status < 500:
        return _class(PERMANENT, f"http_{http_status}")
    if timeout_like and not request_sent:
        return _class(TRANSIENT, "timeout_before_send")
    if connect_like and not request_sent:
        return _class(RETRYABLE, "connect_error_before_send")
    if getattr(exc, "stale", False) is True:
        return _class(PERMANENT, "stale_remote")
    if "ambiguous" in message:
        return _class(AMBIGUOUS_EXTERNAL_EFFECT, "ambiguous_marked")
    return _class(NON_RETRYABLE, "unclassified_non_retryable")


def classify_terminal_policy(reason: str = "digest_mismatch") -> FailureClassification:
    """G0/G1 / digest mismatch: terminal policy, never a Gitea retry."""
    return _class(TERMINAL_POLICY, reason)


def classify_manual_intervention(reason: str = "EXTERNAL_STATE_CONFLICT") -> FailureClassification:
    return _class(MANUAL_INTERVENTION, reason)


def _class(retry_class: RetryClass, reason: str) -> FailureClassification:
    canonical = canonical_retry_class(retry_class)
    terminal = canonical == PERMANENT or retry_class in {TERMINAL_POLICY, MANUAL_INTERVENTION}
    return FailureClassification(
        retry_class=retry_class,
        canonical_class=canonical,
        requires_reconcile=canonical == AMBIGUOUS_EXTERNAL_EFFECT,
        retryable=canonical == TRANSIENT,
        terminal=terminal,
        reason=reason,
    )


def retry_policy_for(
    scope: str,
    policy: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    merged = dict(DEFAULT_RETRY_POLICY)
    if policy:
        for key, value in policy.items():
            merged[key] = {**merged.get(key, {}), **value}
    if scope not in merged:
        raise KeyError(scope)
    return dict(merged[scope])


def retry_budget_path(state_root: Path, run_id: str, scope: str) -> Path:
    return Path(state_root) / "transaction" / "retry" / f"{run_id}_{scope}.json"


def record_retry_attempt(
    state_root: Path,
    *,
    run_id: str,
    scope: str,
    policy: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Increment a bounded retry budget. After exhaustion: typed terminal, no infinite retry."""
    import json
    import os

    cfg = retry_policy_for(scope, policy)
    path = retry_budget_path(state_root, run_id, scope)
    path.parent.mkdir(parents=True, exist_ok=True)
    attempts = 0
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            attempts = int(existing.get("attempts") or 0)
        except (json.JSONDecodeError, ValueError, TypeError):
            attempts = 0
    attempts += 1
    max_attempts = int(cfg["max_attempts"])
    exhausted = attempts > max_attempts
    payload = {
        "run_id": run_id,
        "scope": scope,
        "attempts": attempts,
        "max_attempts": max_attempts,
        "exhausted": exhausted,
        "exhaustion_code": cfg["exhaustion_code"] if exhausted else None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)
    return payload


def exhaustion_event_payload(
    budget: Mapping[str, Any],
    *,
    transaction_id: str,
    component: str = "retry",
) -> dict[str, Any]:
    body = {
        "event_type": "RETRY_EXHAUSTED",
        "transaction_id": transaction_id,
        "component": component,
        "run_id": budget.get("run_id"),
        "scope": budget.get("scope"),
        "attempts": budget.get("attempts"),
        "max_attempts": budget.get("max_attempts"),
        "exhaustion_code": budget.get("exhaustion_code"),
        "code": budget.get("exhaustion_code"),
    }
    return {
        **body,
        "event_id": canonical_json_hash(
            {
                "transaction_id": transaction_id,
                "scope": budget.get("scope"),
                "exhaustion_code": budget.get("exhaustion_code"),
            }
        )[:32],
        "payload_digest": canonical_json_hash(body),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "schema_version": "transaction_control_event.v1",
    }


def new_operator_event_id() -> str:
    return uuid4().hex[:32]
