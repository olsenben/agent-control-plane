"""Probe OpenAI-compatible / Ollama model endpoints."""

from __future__ import annotations

from typing import Any, Literal

import httpx

ModelProbeStatus = Literal["ok", "unreachable", "skipped"]

OLLAMA_PROBE_PATHS = ("/api/version", "/api/tags")
OPENAI_PROBE_PATH = "/models"


def _probe_paths(base_url: str) -> tuple[str, ...]:
    if "/v1" in base_url.rstrip("/"):
        return (OPENAI_PROBE_PATH,)
    return OLLAMA_PROBE_PATHS


def _auth_headers(api_key: str | None) -> dict[str, str]:
    if not api_key:
        return {}
    return {"Authorization": f"Bearer {api_key}"}


def probe_model(
    base_url: str,
    timeout_seconds: float = 3.0,
    *,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Return structured probe result; never raises."""
    url = base_url.strip()
    if not url:
        return {"status": "skipped", "url": ""}

    base = url.rstrip("/")
    last_error = "no response"
    headers = _auth_headers(api_key)

    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            for path in _probe_paths(base):
                try:
                    response = client.get(f"{base}{path}", headers=headers)
                    if response.status_code in (401, 403):
                        last_error = f"http {response.status_code} unauthorized"
                        continue
                    if response.status_code < 500:
                        return {"status": "ok", "url": base, "path": path}
                    last_error = f"http {response.status_code}"
                except httpx.ConnectError as exc:
                    last_error = str(exc) or "connection refused"
                except httpx.TimeoutException:
                    last_error = "timed out"
                except httpx.HTTPError as exc:
                    last_error = str(exc)
    except Exception as exc:  # noqa: BLE001 — probe must not crash callers
        last_error = str(exc)

    return {"status": "unreachable", "url": base, "error": last_error}
