"""Tests for model health probes and readiness."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from agent_control.config import Settings
from agent_control.model_health import probe_model
from agent_control.model_router import ping_role
from agent_control.readiness import build_readiness_report
from agent_control.webhook_server import create_app


def test_probe_model_skipped_when_empty() -> None:
    assert probe_model("")["status"] == "skipped"


def test_probe_model_ok() -> None:
    with patch("httpx.Client") as client_cls:
        client = MagicMock()
        client_cls.return_value.__enter__.return_value = client
        response = MagicMock(status_code=200)
        client.get.return_value = response
        result = probe_model("http://gpu.example:11434")
    assert result["status"] == "ok"


def test_probe_model_openai_path() -> None:
    with patch("httpx.Client") as client_cls:
        client = MagicMock()
        client_cls.return_value.__enter__.return_value = client
        response = MagicMock(status_code=200)
        client.get.return_value = response
        result = probe_model("https://api.openai.com/v1")
    assert result["status"] == "ok"
    client.get.assert_called_once_with(
        "https://api.openai.com/v1/models",
        headers={},
    )


def test_probe_model_sends_bearer_token() -> None:
    with patch("httpx.Client") as client_cls:
        client = MagicMock()
        client_cls.return_value.__enter__.return_value = client
        response = MagicMock(status_code=200)
        client.get.return_value = response
        probe_model("https://api.openai.com/v1", api_key="sk-test")
    client.get.assert_called_once_with(
        "https://api.openai.com/v1/models",
        headers={"Authorization": "Bearer sk-test"},
    )


def test_probe_model_unauthorized() -> None:
    with patch("httpx.Client") as client_cls:
        client = MagicMock()
        client_cls.return_value.__enter__.return_value = client
        response = MagicMock(status_code=401)
        client.get.return_value = response
        result = probe_model("https://api.openai.com/v1", api_key="bad")
    assert result["status"] == "unreachable"
    assert "401" in result["error"]


def test_probe_model_unreachable_connection() -> None:
    with patch("httpx.Client") as client_cls:
        client = MagicMock()
        client_cls.return_value.__enter__.return_value = client
        client.get.side_effect = httpx.ConnectError("connection refused")
        result = probe_model("http://gpu.example:11434")
    assert result["status"] == "unreachable"
    assert "connection refused" in result["error"]


def test_probe_model_unreachable_timeout() -> None:
    with patch("httpx.Client") as client_cls:
        client = MagicMock()
        client_cls.return_value.__enter__.return_value = client
        client.get.side_effect = httpx.TimeoutException("timed out")
        result = probe_model("http://gpu.example:11434")
    assert result["status"] == "unreachable"
    assert result["error"] == "timed out"


def test_readyz_degraded_when_gpus_down(tmp_path: Path) -> None:
    settings = Settings(
        GITEA_WEBHOOK_SECRET="secret",
        AGENT_STATE_ROOT=str(tmp_path / "state"),
        REDIS_URL="redis://localhost:9/0",
        MODEL_3080_BASE_URL="http://3080:11434",
        MODEL_2070_BASE_URL="http://2070:11434",
    )
    with (
        patch("agent_control.readiness.check_redis", return_value={"status": "ok"}),
        patch("agent_control.readiness.probe_model", return_value={"status": "unreachable", "error": "down"}),
    ):
        body, code = build_readiness_report(settings)
    assert code == 200
    assert body["status"] == "degraded"


def test_readyz_strict_503_when_gpu_down(tmp_path: Path) -> None:
    settings = Settings(
        GITEA_WEBHOOK_SECRET="secret",
        AGENT_STATE_ROOT=str(tmp_path / "state"),
        REDIS_URL="redis://localhost:9/0",
        MODEL_3080_BASE_URL="http://3080:11434",
    )
    with (
        patch("agent_control.readiness.check_redis", return_value={"status": "ok"}),
        patch("agent_control.readiness.probe_model", return_value={"status": "unreachable", "error": "down"}),
    ):
        body, code = build_readiness_report(settings, strict=True)
    assert code == 503
    assert body["status"] == "not_ready"


def test_readyz_not_ready_when_redis_fails(tmp_path: Path) -> None:
    settings = Settings(
        AGENT_STATE_ROOT=str(tmp_path / "state"),
        REDIS_URL="redis://localhost:9/0",
    )
    with patch("agent_control.readiness.check_redis", return_value={"status": "error", "error": "no redis"}):
        body, code = build_readiness_report(settings)
    assert code == 503
    assert body["status"] == "not_ready"


def test_readyz_endpoint_degraded(tmp_path: Path) -> None:
    settings = Settings(
        GITEA_WEBHOOK_SECRET="secret",
        AGENT_STATE_ROOT=str(tmp_path / "state"),
        REDIS_URL="redis://localhost:9/0",
        MODEL_3080_BASE_URL="http://3080:11434",
    )
    app = create_app(settings)
    with (
        patch("agent_control.readiness.check_redis", return_value={"status": "ok"}),
        patch("agent_control.readiness.probe_model", return_value={"status": "unreachable", "error": "down"}),
    ):
        client = TestClient(app)
        response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"


def test_model_ping_exits_unreachable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        MODEL_3080_BASE_URL="http://3080:11434",
    )
    monkeypatch.setattr("agent_control.model_router.get_settings", lambda: settings)
    with patch("agent_control.model_router.probe_model", return_value={"status": "unreachable", "error": "down", "url": "http://3080:11434"}):
        result = ping_role("planner", settings)
    assert result["status"] == "unreachable"
