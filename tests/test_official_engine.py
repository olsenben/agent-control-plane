"""Tests for OfficialRLMEngine (Spike 1 candidate)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent_control.model_router import ResolvedEndpoint
from agent_workers.rlm.constants import ENGINE_OFFICIAL
from agent_workers.rlm.engine import get_engine, resolve_engine_name
from agent_workers.rlm.official_engine import OfficialRLMEngine, gather_read_only_context


def _inspect_job() -> dict:
    return {
        "run_id": "run-spike1",
        "session_id": "run-spike1",
        "project": "ai-sdlc-lab/demo-app",
        "flow": "inspect",
        "agent": "explainer",
        "risk_class": "read_only",
        "workflow_definition": "inspect",
        "flow_config_id": "inspect",
        "flow_version": "v1",
        "command_intent": {"kind": "inspect", "natural_language_task": "why idle"},
        "safety": {"command_scope": "inspect"},
        "limits": {"max_iterations": 3, "max_depth": 0},
    }


def test_get_engine_official_returns_official_engine() -> None:
    engine = get_engine("official")
    assert engine.name == ENGINE_OFFICIAL
    assert isinstance(engine, OfficialRLMEngine)


def test_official_engine_rejects_non_read_only_kind(tmp_path: Path) -> None:
    engine = OfficialRLMEngine()
    job = _inspect_job()
    job["command_intent"]["kind"] = "review"
    with pytest.raises(ValueError, match="inspect/explain"):
        engine.run(job, tmp_path, {})


def test_official_engine_single_shot_mock(tmp_path: Path) -> None:
    engine = OfficialRLMEngine()
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "README.md").write_text("# Demo\nService idle because worker offline.", encoding="utf-8")

    endpoint = ResolvedEndpoint(
        role="rlm",
        tier="3080",
        provider="gpu",
        base_url="http://127.0.0.1:11434",
        model="llama3",
        api_key="",
        primary_provider="gpu",
    )

    with patch("agent_workers.rlm.official_engine._rlms_available", return_value=False):
        with patch("agent_workers.rlm.official_engine.resolve_role_primary", return_value=endpoint):
            with patch(
                "agent_workers.rlm.official_engine.chat_completion",
                return_value={"content": "Worker state is idle.", "provider": "gpu", "base_url": endpoint.base_url, "usage": {}},
            ) as mock_chat:
                result = engine.run(
                    _inspect_job(),
                    workspace,
                    {},
                    artifact_dir=str(tmp_path),
                )

    assert result.engine == ENGINE_OFFICIAL
    assert "idle" in result.summary.lower()
    mock_chat.assert_called_once()
    trace_lines = (tmp_path / "rlm_trace.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(trace_lines) >= 2
    assert any("context_gathered" in line or "single_shot" in line for line in trace_lines)


def test_gather_read_only_context_respects_broker(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "README.md").write_text("hello", encoding="utf-8")
    broker = MagicMock()
    broker.workspace = workspace
    broker.read_file.side_effect = lambda path, reason="": {
        "path": path,
        "content": "hello" if path == "README.md" else "",
        "missing": path != "README.md",
    }
    text, sources = gather_read_only_context(broker, max_files=3, max_chars=1000)
    assert "hello" in text
    assert sources == ["README.md"]
