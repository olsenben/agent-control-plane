"""OpenAI-compatible chat completion helper for read-only RLM engines."""

from __future__ import annotations

from typing import Any

import httpx

from agent_control.model_router import ResolvedEndpoint


def normalize_v1_base_url(base_url: str) -> str:
    url = base_url.rstrip("/")
    if url.endswith("/v1"):
        return url
    return f"{url}/v1"


def chat_completion(
    endpoint: ResolvedEndpoint,
    *,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 1024,
    timeout_seconds: float = 120.0,
    response_format: dict[str, Any] | str | None = None,
    stream: bool = False,
) -> dict[str, Any]:
    base = normalize_v1_base_url(endpoint.base_url)
    url = f"{base}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if endpoint.api_key:
        headers["Authorization"] = f"Bearer {endpoint.api_key}"
    payload: dict[str, Any] = {
        "model": endpoint.model or "llama3",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
        "stream": stream,
    }
    if response_format is not None:
        payload["format"] = response_format
    response = httpx.post(url, json=payload, headers=headers, timeout=timeout_seconds)
    response.raise_for_status()
    data = response.json()
    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage") or {}
    return {
        "content": content,
        "model": endpoint.model or data.get("model"),
        "provider": endpoint.provider,
        "base_url": endpoint.base_url,
        "usage": usage,
        "response_format_mode": (
            "schema" if isinstance(response_format, dict) else response_format or "none"
        ),
    }
