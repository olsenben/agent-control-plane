"""Tests for OfficialRLMEngine (Spike 1 candidate)."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent_workers.rlm.model_routing import WorkerResolvedEndpoint
from agent_shared.models.context_pack import ContextPack
from agent_shared.models.review import BlastRadiusContext
from agent_workers.rlm.constants import ENGINE_OFFICIAL
from agent_workers.rlm.engine import get_engine
from agent_workers.rlm.official_engine import OfficialRLMEngine, gather_read_only_context


from contextlib import contextmanager


def _gpu_endpoint() -> WorkerResolvedEndpoint:
    return WorkerResolvedEndpoint(
        provider="gpu",
        base_url="http://127.0.0.1:11434",
        model="llama3",
        api_key="",
    )


@contextmanager
def _patch_gpu_endpoint():
    ep = _gpu_endpoint()
    targets = (
        "agent_workers.rlm.official_engine.resolve_rlm_gpu_endpoint",
        "agent_workers.rlm.model_routing.resolve_rlm_gpu_endpoint",
        "agent_workers.rlm.quality_loop.resolve_rlm_gpu_endpoint",
    )
    active = [patch(target, return_value=ep) for target in targets]
    for item in active:
        item.start()
    try:
        yield
    finally:
        for item in reversed(active):
            item.stop()


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


def test_official_engine_rejects_unsupported_kind(tmp_path: Path) -> None:
    engine = OfficialRLMEngine()
    job = _inspect_job()
    job["command_intent"]["kind"] = "verify"
    with pytest.raises(ValueError, match="inspect/explain/review/plan and fix"):
        engine.run(job, tmp_path, {})


def test_official_engine_rejects_fix_wrong_risk_class(tmp_path: Path) -> None:
    engine = OfficialRLMEngine()
    job = _inspect_job()
    job["command_intent"]["kind"] = "fix"
    with pytest.raises(ValueError, match="write_patch"):
        engine.run(job, tmp_path, {})


def _review_job() -> dict:
    return {
        "run_id": "run-review1",
        "session_id": "run-review1",
        "project": "ai-sdlc-lab/demo-app",
        "flow": "review",
        "agent": "reviewer",
        "risk_class": "read_only_with_repo_context",
        "workflow_definition": "code_review/v1",
        "flow_config_id": "code_review",
        "flow_version": "v1",
        "command_intent": {"kind": "review", "natural_language_task": "review this change"},
        "safety": {"command_scope": "review"},
        "limits": {"max_iterations": 3, "max_depth": 0},
    }


def _plan_job() -> dict:
    return {
        "run_id": "run-plan1",
        "session_id": "run-plan1",
        "project": "ai-sdlc-lab/demo-app",
        "flow": "plan",
        "agent": "planner",
        "risk_class": "planning_only",
        "workflow_definition": "plan/v1",
        "flow_config_id": "plan",
        "flow_version": "v1",
        "command_intent": {"kind": "plan", "natural_language_task": "plan the fix"},
        "safety": {"command_scope": "plan"},
        "limits": {"max_iterations": 3, "max_depth": 0},
    }


def test_official_engine_review_mock(tmp_path: Path) -> None:
    engine = OfficialRLMEngine()
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "README.md").write_text("# Demo\nAuth module needs review.", encoding="utf-8")

    review_json = (
        '{"findings":[{"id":"F-001","severity":"info","summary":"Auth looks ok","file":"README.md",'
        '"confidence":0.8,"risk_tags":[]}],'
        '"files_inspected":["README.md"],'
        '"blast_radius":{"missing_graph_edges":["not implemented"]},'
        '"confidence":"medium","recommended_next_command":"/agent plan","risk_tags":[]}'
    )

    with patch("agent_workers.rlm.official_engine._rlms_available", return_value=False):
        with _patch_gpu_endpoint():
            with patch(
                "agent_workers.rlm.official_engine.chat_completion",
                return_value={"content": review_json, "provider": "gpu", "base_url": _gpu_endpoint().base_url, "usage": {}},
            ):
                result = engine.run(
                    _review_job(),
                    workspace,
                    {},
                    artifact_dir=str(tmp_path),
                )

    assert result.engine == ENGINE_OFFICIAL
    assert result.review_result is not None
    assert result.review_result.findings[0].id == "F-001"
    assert "## Agent Review" in result.summary
    assert "### Finding" in result.summary
    assert "missing_graph_edges: not implemented" in result.summary


def test_official_engine_rejects_review_wrong_risk_class(tmp_path: Path) -> None:
    engine = OfficialRLMEngine()
    job = _review_job()
    job["risk_class"] = "read_only"
    with pytest.raises(ValueError, match="read_only_with_repo_context"):
        engine.run(job, tmp_path, {})


def test_official_engine_single_shot_mock(tmp_path: Path) -> None:
    engine = OfficialRLMEngine()
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "README.md").write_text("# Demo\nService idle because worker offline.", encoding="utf-8")

    with patch("agent_workers.rlm.official_engine._rlms_available", return_value=False):
        with _patch_gpu_endpoint():
            with patch(
                "agent_workers.rlm.official_engine.chat_completion",
                return_value={"content": "Worker state is idle.", "provider": "gpu", "base_url": _gpu_endpoint().base_url, "usage": {}},
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


def test_official_engine_plan_parse_failure_writes_artifact(tmp_path: Path) -> None:
    engine = OfficialRLMEngine()
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "README.md").write_text("# Demo", encoding="utf-8")

    pack = ContextPack(
        project="ai-sdlc-lab/demo-app",
        blast_radius=BlastRadiusContext(
            affected_repos=["ai-sdlc-lab/agent-control-plane"],
            affected_tests=["tests/test_plan_parser.py"],
        ),
        context_sources=["graph:blast_radius"],
    )
    job = _plan_job()
    job["context_pack"] = pack.model_dump(mode="json")

    from agent_shared.models.parse_failure import ParseFailureArtifact
    from agent_workers.rlm.model_output import StructuredParseFailure
    from agent_workers.rlm.plan_parser import PlanParseError

    failure = ParseFailureArtifact(
        run_id=job["run_id"],
        command_kind="plan",
        parse_errors=["forced parse failure"],
        context_sources=list(pack.context_sources),
        blast_radius=pack.blast_radius,
    )

    def _boom(*_a, **_k):
        raise PlanParseError("Could not parse plan output") from StructuredParseFailure(failure)

    with patch("agent_workers.rlm.official_engine._rlms_available", return_value=False):
        with _patch_gpu_endpoint():
            with patch("agent_workers.rlm.quality_loop.resolve_rlm_external_endpoint", return_value=None):
                with patch(
                    "agent_workers.rlm.official_engine.chat_completion",
                    return_value={
                        "content": "{}",
                        "provider": "gpu",
                        "base_url": _gpu_endpoint().base_url,
                        "usage": {},
                    },
                ):
                    with patch("agent_workers.rlm.official_engine.parse_plan_output", side_effect=_boom):
                        with pytest.raises(ValueError, match="Failed to parse plan output"):
                            engine.run(job, workspace, {}, artifact_dir=str(tmp_path))

    artifact_path = tmp_path / "parse_failure.json"
    assert artifact_path.exists()
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["schema_version"] == "parse_failure.v1"
    assert artifact["command_kind"] == "plan"
    assert artifact["status"] == "failed_structured_parse"
    assert artifact["blast_radius"]["affected_repos"] == pack.blast_radius.affected_repos
    assert artifact["context_sources"] == pack.context_sources


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


def test_official_engine_single_shot_uses_job_timeout(tmp_path: Path) -> None:
    engine = OfficialRLMEngine()
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "README.md").write_text("# Demo", encoding="utf-8")

    job = _inspect_job()
    job["limits"]["time_budget_seconds"] = 300

    with patch("agent_workers.rlm.official_engine._rlms_available", return_value=False):
        with _patch_gpu_endpoint():
            with patch(
                "agent_workers.rlm.official_engine.chat_completion",
                return_value={"content": "ok", "provider": "gpu", "base_url": _gpu_endpoint().base_url, "usage": {}},
            ) as mock_chat:
                engine.run(job, workspace, {}, artifact_dir=str(tmp_path))

    mock_chat.assert_called_once()
    assert mock_chat.call_args.kwargs["timeout_seconds"] == 300.0


def test_official_engine_clamps_long_summary(tmp_path: Path) -> None:
    engine = OfficialRLMEngine()
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "README.md").write_text("# Demo", encoding="utf-8")

    long_summary = "x" * 5000

    with patch("agent_workers.rlm.official_engine._rlms_available", return_value=False):
        with _patch_gpu_endpoint():
            with patch(
                "agent_workers.rlm.official_engine.chat_completion",
                return_value={"content": long_summary, "provider": "gpu", "base_url": _gpu_endpoint().base_url, "usage": {}},
            ):
                result = engine.run(_inspect_job(), workspace, {}, artifact_dir=str(tmp_path))

    assert len(result.summary) <= 3500
    assert "truncated to fit Gitea comment limit" in result.summary
