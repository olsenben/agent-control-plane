"""Quality-triggered model fallback tests (Slice 6D.1)."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agent_shared.constants import TERMINAL_STATUS_FAILED_QUALITY_GATE
from agent_shared.models.plan import PlanResult, PlanStep
from agent_workers.rlm.model_routing import WorkerResolvedEndpoint
from agent_workers.rlm.output_quality import evaluate_plan_output_quality
from agent_workers.rlm.quality_loop import run_quality_gated_attempts


def _hollow_plan() -> PlanResult:
    return PlanResult(steps=[], fixable=False, quality_gate_reasons=["Plan has no steps."])


def _good_plan() -> PlanResult:
    return PlanResult(
        steps=[PlanStep(id="S1", summary="Edit README", files=["README.md"])],
        fixable=True,
    )


@pytest.fixture
def gpu_endpoint(monkeypatch: pytest.MonkeyPatch) -> WorkerResolvedEndpoint:
    monkeypatch.setenv("MODEL_3080_BASE_URL", "http://gpu")
    monkeypatch.setenv("MODEL_3080_NAME", "qwen")
    return WorkerResolvedEndpoint(provider="gpu", base_url="http://gpu", model="qwen")


def test_gpu_hollow_then_external_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    gpu_endpoint: WorkerResolvedEndpoint,
) -> None:
    monkeypatch.setenv("MODEL_EXTERNAL_ROLES", "rlm")
    monkeypatch.setenv("MODEL_3080_EXTERNAL_BASE_URL", "http://ext")
    monkeypatch.setenv("MODEL_3080_EXTERNAL_NAME", "gpt")
    calls: list[str] = []

    def call_model(endpoint: WorkerResolvedEndpoint, suffix: str) -> str:
        calls.append(endpoint.provider)
        return "raw"

    attempt = {"n": 0}

    def parse_and_finalize(raw: str, _endpoint) -> tuple[str, PlanResult, list[str]]:
        attempt["n"] += 1
        if attempt["n"] < 3:
            return "hollow", _hollow_plan(), []
        return "ok", _good_plan(), []

    failed, success = run_quality_gated_attempts(
        kind="plan",
        job={
            "run_id": "run-qf",
            "session_id": "run-qf",
            "project": "p/r",
            "flow": "planner",
            "agent": "planner",
            "risk_class": "planning_only",
            "workflow_definition": "planner/v1",
            "flow_config_id": "planner",
            "flow_version": "0.1.0",
        },
        artifact_dir=str(tmp_path),
        engine_name="official_rlm",
        call_model=call_model,
        parse_and_finalize=parse_and_finalize,
    )
    assert failed is None
    assert success is not None
    assert success.ok
    assert isinstance(success.parsed, PlanResult)
    assert evaluate_plan_output_quality(success.parsed).passed
    assert "external" in calls


def test_all_hollow_fails_quality_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    gpu_endpoint: WorkerResolvedEndpoint,
) -> None:
    monkeypatch.delenv("MODEL_EXTERNAL_ROLES", raising=False)
    monkeypatch.delenv("MODEL_3080_EXTERNAL_BASE_URL", raising=False)

    def call_model(_endpoint: WorkerResolvedEndpoint, _suffix: str) -> str:
        return "raw"

    def parse_and_finalize(raw: str, _endpoint) -> tuple[str, PlanResult, list[str]]:
        return "hollow", _hollow_plan(), []

    failed, success = run_quality_gated_attempts(
        kind="plan",
        job={
            "run_id": "run-hollow",
            "session_id": "run-hollow",
            "project": "p/r",
            "flow": "planner",
            "agent": "planner",
            "risk_class": "planning_only",
            "workflow_definition": "planner/v1",
            "flow_config_id": "planner",
            "flow_version": "0.1.0",
        },
        artifact_dir=str(tmp_path),
        engine_name="official_rlm",
        call_model=call_model,
        parse_and_finalize=parse_and_finalize,
    )
    assert success is None
    assert failed is not None
    assert failed.status == "failed"
    assert failed.terminal_status == TERMINAL_STATUS_FAILED_QUALITY_GATE
    qg = json.loads((tmp_path / "quality_gate_result.json").read_text(encoding="utf-8"))
    assert qg["passed"] is False


def test_external_fallback_unconfigured_fails_visibly_not_completed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    gpu_endpoint: WorkerResolvedEndpoint,
) -> None:
    monkeypatch.delenv("MODEL_EXTERNAL_ROLES", raising=False)

    failed, _ = run_quality_gated_attempts(
        kind="plan",
        job={
            "run_id": "run-no-ext",
            "session_id": "run-no-ext",
            "project": "p/r",
            "flow": "planner",
            "agent": "planner",
            "risk_class": "planning_only",
            "workflow_definition": "planner/v1",
            "flow_config_id": "planner",
            "flow_version": "0.1.0",
        },
        artifact_dir=str(tmp_path),
        engine_name="official_rlm",
        call_model=MagicMock(return_value="x"),
        parse_and_finalize=lambda _r, _e: ("h", _hollow_plan(), []),
    )
    assert failed is not None
    assert failed.status == "failed"
    assert failed.terminal_status == TERMINAL_STATUS_FAILED_QUALITY_GATE
    assert failed.status != "completed"


def test_quality_gate_result_json_written_for_empty_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    gpu_endpoint: WorkerResolvedEndpoint,
) -> None:
    monkeypatch.delenv("MODEL_EXTERNAL_ROLES", raising=False)
    run_quality_gated_attempts(
        kind="plan",
        job={
            "run_id": "run-art",
            "session_id": "run-art",
            "project": "p/r",
            "flow": "planner",
            "agent": "planner",
            "risk_class": "planning_only",
            "workflow_definition": "planner/v1",
            "flow_config_id": "planner",
            "flow_version": "0.1.0",
        },
        artifact_dir=str(tmp_path),
        engine_name="official_rlm",
        call_model=MagicMock(return_value="x"),
        parse_and_finalize=lambda _r, _e: ("h", _hollow_plan(), []),
    )
    assert (tmp_path / "quality_gate_result.json").is_file()
