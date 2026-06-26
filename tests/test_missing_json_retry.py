"""Missing-JSON retry tests (Slice 5.1)."""

from unittest.mock import MagicMock, patch

import pytest

from agent_control.model_router import ResolvedEndpoint
from agent_shared.models.context_pack import ContextPack
from agent_workers.rlm.model_output import StructuredParseFailure, validate_or_repair


def _endpoint() -> ResolvedEndpoint:
    return ResolvedEndpoint(
        role="rlm",
        tier="3080",
        provider="gpu",
        base_url="http://localhost:11434",
        model="m",
        api_key="",
        primary_provider="gpu",
    )


def test_missing_json_retry_succeeds_on_second_attempt() -> None:
    endpoint = _endpoint()
    calls: list[str] = []

    def _fake_json_retry(**kwargs):
        calls.append("json_retry")
        return '{"steps": [{"id": "S1", "summary": "do", "files": ["README.md"]}], "confidence": "high", "recommended_next_command": "/agent fix", "risk_tags": []}'

    with patch("agent_workers.rlm.model_output.attempt_json_only_retry", side_effect=_fake_json_retry):
        result = validate_or_repair(
            "plan",
            "This is prose only, not JSON.",
            context_pack=ContextPack(project="ai-sdlc-lab/demo"),
            run_id="run-1",
            json_retry_endpoint=endpoint,
            repair_endpoint=endpoint,
        )
    assert calls == ["json_retry"]
    assert result.steps[0].id == "S1"


def test_missing_json_retry_then_repair_still_fails() -> None:
    endpoint = _endpoint()

    with patch("agent_workers.rlm.model_output.attempt_json_only_retry", return_value="still prose"):
        with patch("agent_workers.rlm.model_output.attempt_missing_json_repair", return_value="also prose"):
            with pytest.raises(StructuredParseFailure):
                validate_or_repair(
                    "fix",
                    "no json here",
                    run_id="run-2",
                    json_retry_endpoint=endpoint,
                    repair_endpoint=endpoint,
                )
