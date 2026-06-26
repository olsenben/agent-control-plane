"""StructuredOutputClient provider fallback tests."""

from unittest.mock import patch

from agent_control.model_router import ResolvedEndpoint
from agent_workers.rlm.structured_output_client import StructuredOutputClient


def test_structured_provider_fallback_when_instructor_missing(monkeypatch) -> None:
    monkeypatch.setenv("STRUCTURED_OUTPUT_PROVIDER", "instructor_ollama")
    with patch.object(StructuredOutputClient, "_instructor_available", return_value=False):
        client = StructuredOutputClient()
    assert client.provider == "native_ollama_schema"


def test_native_provider_used_by_default(monkeypatch) -> None:
    monkeypatch.delenv("STRUCTURED_OUTPUT_PROVIDER", raising=False)
    endpoint = ResolvedEndpoint(
        role="rlm",
        tier="3080",
        provider="gpu",
        base_url="http://localhost:11434",
        model="m",
        api_key="",
        primary_provider="gpu",
    )
    with patch("agent_workers.rlm.structured_output_client.chat_completion") as mock_chat:
        mock_chat.return_value = {"content": "{}", "provider": "ollama", "base_url": endpoint.base_url}
        client = StructuredOutputClient()
        result = client.complete(
            endpoint=endpoint,
            system_prompt="sys",
            user_prompt="user",
            response_format="json",
            timeout_seconds=30.0,
        )
    assert result["structured_output_provider"] == "native_ollama_schema"
    mock_chat.assert_called_once()
