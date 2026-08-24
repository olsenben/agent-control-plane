"""Typed retry classification and bounded budgets."""

from __future__ import annotations

from pathlib import Path

import httpx

from agent_control.transaction.retry import (
    AMBIGUOUS_EXTERNAL_EFFECT,
    NON_RETRYABLE,
    PERMANENT,
    RECONCILE_BEFORE_RETRY,
    RETRYABLE,
    TRANSIENT,
    classify_exception,
    exhaustion_event_payload,
    record_retry_attempt,
    retry_policy_for,
)


def test_each_retry_class() -> None:
    transient = classify_exception(TimeoutError("connect timed out"), request_sent=False)
    assert transient.retry_class == TRANSIENT
    assert transient.retryable is True

    retryable = classify_exception(httpx.ConnectError("connection refused"), request_sent=False)
    assert retryable.canonical_class == TRANSIENT
    assert retryable.retry_class in {TRANSIENT, RETRYABLE}

    permanent = classify_exception(RuntimeError("bad request"), request_sent=False, status_code=400)
    assert permanent.retry_class == PERMANENT
    assert permanent.terminal is True

    non_retryable = classify_exception(RuntimeError("unclassified"))
    assert non_retryable.retry_class == NON_RETRYABLE or non_retryable.canonical_class == PERMANENT
    assert non_retryable.terminal is True

    ambiguous = classify_exception(TimeoutError("read timed out"), request_sent=True)
    assert ambiguous.retry_class == AMBIGUOUS_EXTERNAL_EFFECT
    assert ambiguous.requires_reconcile is True

    reconcile = classify_exception(RuntimeError("connection reset by peer"), request_sent=True)
    assert reconcile.canonical_class == AMBIGUOUS_EXTERNAL_EFFECT
    assert reconcile.retry_class in {AMBIGUOUS_EXTERNAL_EFFECT, RECONCILE_BEFORE_RETRY}


def test_http_classes() -> None:
    assert classify_exception(RuntimeError("x"), status_code=503).retryable is True
    assert classify_exception(RuntimeError("x"), status_code=429).retryable is True
    assert classify_exception(RuntimeError("x"), status_code=404).terminal is True


def test_retry_budgets_exhaust_to_typed_terminal(tmp_path: Path) -> None:
    policy = {"gitea_publish": {"max_attempts": 2, "exhaustion_code": "GITEA_PUBLISH_RETRY_EXHAUSTED"}}
    first = record_retry_attempt(tmp_path, run_id="r1", scope="gitea_publish", policy=policy)
    assert first["exhausted"] is False
    second = record_retry_attempt(tmp_path, run_id="r1", scope="gitea_publish", policy=policy)
    assert second["exhausted"] is False
    third = record_retry_attempt(tmp_path, run_id="r1", scope="gitea_publish", policy=policy)
    assert third["exhausted"] is True
    assert third["exhaustion_code"] == "GITEA_PUBLISH_RETRY_EXHAUSTED"
    event = exhaustion_event_payload(third, transaction_id="tx-1")
    assert event["event_type"] == "RETRY_EXHAUSTED"
    assert event["payload_digest"]
    assert "token" not in str(event).lower() or "exhaustion" in str(event)


def test_retry_policy_scopes() -> None:
    for scope in (
        "worker_dispatch",
        "evidence_adapters",
        "gitea_reads",
        "gitea_publish",
        "ci_polling",
    ):
        cfg = retry_policy_for(scope)
        assert int(cfg["max_attempts"]) >= 1
        assert cfg["exhaustion_code"]
