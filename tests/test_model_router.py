"""Tests for model role routing and fallback."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from agent_control.config import Settings
from agent_control.model_router import (
    ping_role,
    resolve_role,
    resolve_role_primary,
)


def _settings(**kwargs: object) -> Settings:
    return Settings(**kwargs)


def test_resolve_role_primary_3080_gpu() -> None:
    settings = _settings(
        MODEL_3080_BASE_URL="http://3080:11434",
        MODEL_3080_NAME="qwen",
    )
    resolved = resolve_role_primary("planner", settings)
    assert resolved.tier == "3080"
    assert resolved.provider == "gpu"
    assert resolved.primary_provider == "gpu"
    assert resolved.base_url == "http://3080:11434"
    assert resolved.model == "qwen"


def test_resolve_role_primary_external_preference() -> None:
    settings = _settings(
        MODEL_3080_BASE_URL="http://3080:11434",
        MODEL_3080_EXTERNAL_BASE_URL="https://api.openai.com/v1",
        MODEL_3080_EXTERNAL_NAME="gpt-4o-mini",
        MODEL_EXTERNAL_ROLES="judge",
    )
    resolved = resolve_role_primary("judge", settings)
    assert resolved.provider == "external"
    assert resolved.base_url == "https://api.openai.com/v1"
    assert resolved.model == "gpt-4o-mini"


def test_external_preference_ignored_without_external_url() -> None:
    settings = _settings(
        MODEL_3080_BASE_URL="http://3080:11434",
        MODEL_EXTERNAL_ROLES="judge",
    )
    resolved = resolve_role_primary("judge", settings)
    assert resolved.provider == "gpu"


def test_resolve_role_without_probe() -> None:
    settings = _settings(MODEL_3080_BASE_URL="http://3080:11434")
    result = resolve_role("planner", settings, probe=False)
    assert result["provider"] == "gpu"
    assert "status" not in result


def test_resolve_role_fallback_when_primary_unreachable() -> None:
    settings = _settings(
        MODEL_3080_BASE_URL="http://3080:11434",
        MODEL_3080_FALLBACK_BASE_URL="https://api.openai.com/v1",
        MODEL_3080_FALLBACK_NAME="gpt-4o-mini",
        MODEL_FALLBACK_ENABLED=True,
    )

    def fake_probe(url: str, timeout: float, *, api_key: str | None = None) -> dict[str, str]:
        if url == "http://3080:11434":
            return {"status": "unreachable", "url": url, "error": "down"}
        return {"status": "ok", "url": url, "path": "/models"}

    with patch("agent_control.model_router.probe_model", side_effect=fake_probe):
        result = resolve_role("planner", settings)

    assert result["status"] == "ok"
    assert result["provider"] == "fallback"
    assert result["fallback_used"] is True
    assert result["base_url"] == "https://api.openai.com/v1"


def test_resolve_role_no_fallback_when_disabled() -> None:
    settings = _settings(
        MODEL_3080_BASE_URL="http://3080:11434",
        MODEL_3080_FALLBACK_BASE_URL="https://api.openai.com/v1",
        MODEL_FALLBACK_ENABLED=False,
    )
    with patch(
        "agent_control.model_router.probe_model",
        return_value={"status": "unreachable", "url": "http://3080:11434", "error": "down"},
    ):
        result = resolve_role("planner", settings)

    assert result["status"] == "unreachable"
    assert result["provider"] == "gpu"
    assert result["fallback_used"] is False


def test_2070_role_uses_2070_fallback_only() -> None:
    settings = _settings(
        MODEL_2070_BASE_URL="http://2070:11434",
        MODEL_2070_FALLBACK_BASE_URL="https://fallback-2070.example/v1",
        MODEL_3080_FALLBACK_BASE_URL="https://fallback-3080.example/v1",
        MODEL_FALLBACK_ENABLED=True,
    )

    def fake_probe(url: str, timeout: float, *, api_key: str | None = None) -> dict[str, str]:
        if url == "http://2070:11434":
            return {"status": "unreachable", "url": url, "error": "down"}
        return {"status": "ok", "url": url, "path": "/models"}

    with patch("agent_control.model_router.probe_model", side_effect=fake_probe):
        result = resolve_role("worker", settings)

    assert result["provider"] == "fallback"
    assert result["base_url"] == "https://fallback-2070.example/v1"


def test_unknown_role_raises() -> None:
    with pytest.raises(ValueError, match="unknown role"):
        resolve_role_primary("unknown")


def test_ping_role_skipped_when_unconfigured() -> None:
    result = ping_role("planner", _settings())
    assert result["status"] == "skipped"
