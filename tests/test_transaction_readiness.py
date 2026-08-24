"""Nested transaction readiness. CT102 down must not 503 core /readyz."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from agent_control.config import Settings
from agent_control.readiness import build_readiness_report
from agent_control.transaction.readiness import (
    TRANSACTION_CHECK_KEYS,
    check_auto_admit_pipeline,
    collect_transaction_checks,
    worker_durable_credential_readiness,
)
from agent_control.webhook_server import create_app


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    kwargs = {
        "GITEA_WEBHOOK_SECRET": "secret",
        "AGENT_STATE_ROOT": str(tmp_path / "state"),
        "REDIS_URL": "redis://localhost:9/0",
    }
    kwargs.update(overrides)
    return Settings(**kwargs)  # type: ignore[arg-type]


def test_healthz_is_process_liveness_only(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_nested_checks_present_and_gitea_down_does_not_503(tmp_path: Path) -> None:
    settings = _settings(tmp_path, GITEA_BOT_TOKEN="tok")
    gitea_down = {"status": "error", "error": "ConnectError"}
    with (
        patch("agent_control.readiness.check_redis", return_value={"status": "ok"}),
        patch(
            "agent_control.transaction.readiness.check_gitea_reachable",
            return_value=gitea_down,
        ),
    ):
        body, code = build_readiness_report(settings)
    assert code == 200
    assert body["status"] in {"ready", "degraded"}
    txn = body["checks"]["transaction"]
    for key in TRANSACTION_CHECK_KEYS:
        assert key in txn
    assert txn["gitea_reachable"]["status"] == "error"
    assert txn["auto_admit_ready"] is False
    assert txn["auto_admit_pipeline_ready"]["fail_closed"] is True


def test_auto_admit_fail_closed_when_verifier_missing() -> None:
    result = check_auto_admit_pipeline(
        verifier_id=None,
        required_providers_ok=True,
        verifier_reachable=False,
    )
    assert result["auto_admit_ready"] is False
    assert result["authoritative_verifier_present"] is False
    assert result["fail_closed"] is True
    assert result["status"] == "not_ready"


def test_collect_transaction_checks_keys(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    checks = collect_transaction_checks(
        settings,
        gitea_probe={"status": "ok"},
    )
    for key in TRANSACTION_CHECK_KEYS:
        assert key in checks
    assert checks["package_importable"]["status"] == "ok"
    assert checks["frozen_c_loaded"]["status"] == "ok"
    assert checks["evidence_bus"]["status"] == "ok"
    assert checks["durable_state_writable"]["status"] == "ok"
    assert checks["capability_store"]["status"] == "ok"


def test_ct104_worker_readiness_requires_assertion_pass(
    monkeypatch,
) -> None:
    monkeypatch.setenv("WORKER_DURABLE_CREDENTIALS_PRESENT", "NO")
    monkeypatch.delenv("GITEA_BOT_TOKEN", raising=False)
    monkeypatch.delenv("GITEA_AGENT_TOKEN", raising=False)
    result = worker_durable_credential_readiness()
    assert result["ok"] is True
    assert result["WORKER_DURABLE_CREDENTIALS_PRESENT_ASSERTION"] == "PASS"

    monkeypatch.setenv("GITEA_BOT_TOKEN", "secret-should-not-be-logged")
    failed = worker_durable_credential_readiness()
    assert failed["ok"] is False
    assert failed["WORKER_DURABLE_CREDENTIALS_PRESENT_ASSERTION"] == "FAIL"
    dumped = str(failed)
    assert "secret-should-not-be-logged" not in dumped
    assert "GITEA_BOT_TOKEN" in failed["violation_env_names"]
