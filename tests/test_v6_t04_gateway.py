"""V6 T04 — model gateway, attempt budget, egress policy."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_control.config import Settings
from agent_control.model_egress import evaluate_external_egress, repo_allows_external
from agent_control.model_gateway import (
    ModelRouteExhausted,
    chat_completion_with_failover,
    context_controller_policy,
)
from agent_control.model_router import ResolvedEndpoint
from agent_shared.models.model_attempt_budget import AttemptBudgetTracker, ModelAttemptBudget


def test_budget_exhaustion() -> None:
    tracker = AttemptBudgetTracker(
        limits=ModelAttemptBudget(max_total_completion_attempts=2, max_infrastructure_attempts=2)
    )
    assert tracker.consume("infrastructure")
    assert tracker.consume("infrastructure")
    assert not tracker.consume("infrastructure")
    assert tracker.as_dict()["exhausted"] is True


def test_repo_egress_fail_closed() -> None:
    settings = Settings(REPO_EXTERNAL_MODEL_POLICY="")
    assert not repo_allows_external("ai-sdlc-lab/demo-app", settings)
    decision = evaluate_external_egress(
        project="ai-sdlc-lab/demo-app",
        role="reviewer",
        provider="fallback",
        settings=settings,
    )
    assert decision.allowed is False
    assert decision.data_left_homelab is False


def test_repo_egress_allowlist() -> None:
    settings = Settings(
        REPO_EXTERNAL_MODEL_POLICY="ai-sdlc-lab/*",
        MODEL_CODE_HANDLING_ROLES="fixer,rlm",
        MODEL_FALLBACK_ENABLED=True,
    )
    assert repo_allows_external("ai-sdlc-lab/demo-app", settings)
    ok = evaluate_external_egress(
        project="ai-sdlc-lab/demo-app",
        role="reviewer",
        provider="fallback",
        settings=settings,
    )
    assert ok.allowed is True
    denied_fix = evaluate_external_egress(
        project="ai-sdlc-lab/demo-app",
        role="fixer",
        provider="fallback",
        settings=Settings(
            REPO_EXTERNAL_MODEL_POLICY="ai-sdlc-lab/*",
            MODEL_CODE_HANDLING_ROLES="",  # empty -> default includes fixer
            MODEL_FALLBACK_ENABLED=True,
        ),
    )
    # empty MODEL_CODE_HANDLING_ROLES defaults to fixer,rlm allowed
    assert denied_fix.allowed is True


def test_fixer_denied_without_code_role() -> None:
    settings = Settings(
        REPO_EXTERNAL_MODEL_POLICY="*",
        MODEL_CODE_HANDLING_ROLES="reviewer",  # fixer not listed
        MODEL_FALLBACK_ENABLED=True,
    )
    decision = evaluate_external_egress(
        project="ai-sdlc-lab/demo-app",
        role="fixer",
        provider="fallback",
        settings=settings,
    )
    assert decision.allowed is False


def test_context_controller_policy_deterministic() -> None:
    assert context_controller_policy(recursion_needed=False, controller_available=True) == (
        "deterministic_preflight"
    )
    assert context_controller_policy(recursion_needed=True, controller_available=False) == (
        "deterministic_only"
    )
    assert context_controller_policy(recursion_needed=True, controller_available=True) == (
        "litellm_context_controller"
    )


def test_completion_failover_to_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        MODEL_3080_BASE_URL="http://gpu-down:11434",
        MODEL_3080_NAME="qwen",
        MODEL_3080_FALLBACK_BASE_URL="https://api.example.com/v1",
        MODEL_3080_FALLBACK_NAME="gpt-mini",
        MODEL_3080_FALLBACK_API_KEY="sk-test",
        MODEL_FALLBACK_ENABLED=True,
        REPO_EXTERNAL_MODEL_POLICY="ai-sdlc-lab/*",
        MODEL_CODE_HANDLING_ROLES="fixer,rlm,reviewer",
        AGENT_STATE_ROOT=tmp_path,
    )

    calls: list[str] = []

    def fake_complete(endpoint: ResolvedEndpoint, **kwargs):
        calls.append(endpoint.provider)
        if endpoint.provider == "gpu":
            raise ConnectionError("gpu down")
        return {
            "content": "ok",
            "model": endpoint.model,
            "provider": endpoint.provider,
            "base_url": endpoint.base_url,
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }

    result = chat_completion_with_failover(
        "reviewer",
        system_prompt="sys",
        user_prompt="user",
        project="ai-sdlc-lab/demo-app",
        run_id="run-t04",
        state_root=tmp_path,
        settings=settings,
        complete_fn=fake_complete,
    )
    assert result["content"] == "ok"
    assert result["fallback_used"] is True
    assert result["data_left_homelab"] is True
    assert "gpu" in calls and "fallback" in calls


def test_completion_all_routes_failed(tmp_path: Path) -> None:
    settings = Settings(
        MODEL_3080_BASE_URL="http://gpu-down:11434",
        MODEL_3080_NAME="qwen",
        MODEL_FALLBACK_ENABLED=False,
        AGENT_STATE_ROOT=tmp_path,
    )

    def boom(endpoint: ResolvedEndpoint, **kwargs):
        raise TimeoutError("down")

    with pytest.raises(ModelRouteExhausted):
        chat_completion_with_failover(
            "reviewer",
            system_prompt="sys",
            user_prompt="user",
            project="ai-sdlc-lab/demo-app",
            run_id="run-t04-fail",
            state_root=tmp_path,
            settings=settings,
            complete_fn=boom,
        )


def test_egress_blocks_fallback(tmp_path: Path) -> None:
    settings = Settings(
        MODEL_3080_BASE_URL="http://gpu-down:11434",
        MODEL_3080_NAME="qwen",
        MODEL_3080_FALLBACK_BASE_URL="https://api.example.com/v1",
        MODEL_3080_FALLBACK_NAME="gpt-mini",
        MODEL_FALLBACK_ENABLED=True,
        REPO_EXTERNAL_MODEL_POLICY="",  # deny all
        AGENT_STATE_ROOT=tmp_path,
    )

    def boom(endpoint: ResolvedEndpoint, **kwargs):
        raise ConnectionError("gpu down")

    with pytest.raises(ModelRouteExhausted):
        chat_completion_with_failover(
            "reviewer",
            system_prompt="sys",
            user_prompt="user",
            project="ai-sdlc-lab/demo-app",
            run_id="run-t04-egress",
            state_root=tmp_path,
            settings=settings,
            complete_fn=boom,
        )


def test_worker_gateway_prefers_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_GATEWAY_BASE_URL", "http://litellm:4000/v1")
    monkeypatch.setenv("MODEL_GATEWAY_RLM_MODEL", "primary-generator")
    monkeypatch.setenv("MODEL_3080_EXTERNAL_BASE_URL", "https://should-not-use")
    monkeypatch.setenv("MODEL_EXTERNAL_ROLES", "rlm")
    from agent_workers.rlm import model_routing as mr

    ep = mr.resolve_rlm_gpu_endpoint()
    assert ep.provider == "gateway"
    assert ep.base_url.startswith("http://litellm")
    assert mr.resolve_rlm_external_endpoint() is None
