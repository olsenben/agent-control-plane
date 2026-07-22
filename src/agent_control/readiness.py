"""Aggregate readiness checks for /readyz."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import redis

from agent_control.config import Settings
from agent_control.model_health import probe_model
from agent_control.observe_links import observe_public_base_url_configured


def check_redis(redis_url: str) -> dict[str, str]:
    try:
        client = redis.from_url(redis_url, socket_connect_timeout=2)
        client.ping()
        return {"status": "ok"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}


def check_state_dir(state_root: Path) -> dict[str, str]:
    try:
        state_root.mkdir(parents=True, exist_ok=True)
        probe = state_root / ".readyz_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return {"status": "ok"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}


def build_readiness_report(settings: Settings, *, strict: bool = False) -> tuple[dict[str, Any], int]:
    checks: dict[str, Any] = {}

    redis_result = check_redis(settings.redis_url)
    checks["redis"] = redis_result["status"]
    if redis_result.get("error"):
        checks["redis_detail"] = redis_result

    state_result = check_state_dir(settings.agent_state_root)
    checks["state_dir"] = state_result["status"]
    if state_result.get("error"):
        checks["state_dir_detail"] = state_result

    core_ok = checks.get("redis") == "ok" and checks.get("state_dir") == "ok"

    # V9 T06 (H8): informational only -- never gates readiness. Unset is a
    # valid, fail-closed steady state (Observe links are simply omitted).
    checks["observe_public_base_url"] = (
        "configured" if observe_public_base_url_configured(settings) else "unset"
    )

    model_checks: list[tuple[str, dict[str, Any]]] = []
    if settings.model_3080_base_url:
        model_checks.append(
            (
                "model_3080",
                probe_model(
                    settings.model_3080_base_url,
                    settings.model_health_timeout_seconds,
                    api_key=settings.model_3080_api_key or None,
                ),
            )
        )
    else:
        checks["model_3080"] = "skipped"

    if settings.model_2070_base_url:
        model_checks.append(
            (
                "model_2070",
                probe_model(
                    settings.model_2070_base_url,
                    settings.model_health_timeout_seconds,
                    api_key=settings.model_2070_api_key or None,
                ),
            )
        )
    else:
        checks["model_2070"] = "skipped"

    optional_model_checks = [
        ("model_3080_external", settings.model_3080_external_base_url, settings.model_3080_external_api_key),
        ("model_3080_fallback", settings.model_3080_fallback_base_url, settings.model_3080_fallback_api_key),
        ("model_2070_external", settings.model_2070_external_base_url, settings.model_2070_external_api_key),
        ("model_2070_fallback", settings.model_2070_fallback_base_url, settings.model_2070_fallback_api_key),
    ]
    for name, url, api_key in optional_model_checks:
        if url:
            checks[name] = probe_model(url, settings.model_health_timeout_seconds, api_key=api_key or None)
        else:
            checks[name] = "skipped"

    models_all_ok = True
    models_any_configured = False
    for name, result in model_checks:
        models_any_configured = True
        checks[name] = result
        if result.get("status") != "ok":
            models_all_ok = False

    if not core_ok:
        return {"status": "not_ready", "checks": checks}, 503

    if strict and models_any_configured and not models_all_ok:
        return {"status": "not_ready", "checks": checks, "reason": "strict model check failed"}, 503

    if models_any_configured and not models_all_ok:
        return {"status": "degraded", "checks": checks}, 200

    return {"status": "ready", "checks": checks}, 200
