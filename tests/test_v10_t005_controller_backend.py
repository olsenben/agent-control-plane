"""V10 T00.5 — C0/C1 recursive controller backend selection and telemetry truth.

Gate G2: `deterministic` (C0) must never touch a model; `model` (C1) must prove
a live controller call in telemetry, and must fail soft back to C0 semantics
rather than losing the recursive_context_result.v1 artifact.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agent_control.config import Settings
from agent_control.memory.preflight import compile_memory_preflight
from agent_control.model_gateway import ModelRouteExhausted
from agent_control.recursive_context.config import resolve_controller_backend
from agent_control.recursive_context.telemetry import controller_telemetry_payload
from agent_control.recursive_context.worker import run_conditional_recursive_context
from agent_shared.models.jobs import TriggerContext
from agent_shared.models.memory_preflight import (
    THRESHOLD_MISSING_GRAPH_EDGES,
    MemoryPreflight,
)
from agent_shared.models.recursive_context import SCHEMA_VERSION, RecursiveContextResult
from support.policy_pin import install_fake_policy_pin

BACKEND_ENV = "RECURSIVE_CONTEXT_CONTROLLER_BACKEND"
GATEWAY_PATH = "agent_control.recursive_context.model_client.chat_completion_with_failover"


def _patch_gateway(monkeypatch: pytest.MonkeyPatch, fake: Any) -> Any:
    """Patch by dotted path.

    Another test drops every ``recursive_context`` module from ``sys.modules``
    to prove prepare-dispatch stays lazy, so a module object captured at import
    time can be stale by the time the worker re-imports the controller client.
    """
    monkeypatch.setattr(GATEWAY_PATH, fake)
    return fake


def _tc(*, issue: int = 2) -> TriggerContext:
    return TriggerContext(
        event_type="gitea.issue_comment",
        issue_number=issue,
        author="alice",
        raw_body="/agent review",
        normalized_body="/agent review",
    )


@pytest.fixture
def state_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    state = tmp_path / "agent-state"
    runs = tmp_path / "agent-runs"
    state.mkdir()
    runs.mkdir()
    monkeypatch.setenv("AGENT_STATE_ROOT", str(state))
    monkeypatch.setenv("AGENT_RUNS_DIR", str(runs))
    monkeypatch.setenv("AGENT_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("MODEL_ROUTING_POLICY", "fake")
    monkeypatch.setenv("MODEL_2070_BASE_URL", "http://model-2070.invalid:11434")
    monkeypatch.setenv("MODEL_2070_NAME", "qwen2.5-coder:3b")
    monkeypatch.delenv(BACKEND_ENV, raising=False)
    install_fake_policy_pin(monkeypatch)
    return state


class _GatewaySpy:
    """Stand-in for `chat_completion_with_failover` at the 2070 role."""

    def __init__(self, *, content: str = "H1 is supported by graph:blast_radius.") -> None:
        self.calls: list[dict[str, Any]] = []
        self.content = content

    def __call__(self, role: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"role": role, **kwargs})
        return {
            "content": self.content,
            "model": "qwen2.5-coder:3b",
            "provider": "gpu",
            "usage": {"prompt_tokens": 231, "completion_tokens": 47, "eval_duration": 1_500_000_000},
            "data_left_homelab": False,
        }


class _GatewayDown:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, role: str, **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        raise ModelRouteExhausted(f"all model routes failed for role={role}")


def _qualifying_preflight(session, *, required: bool = True) -> MemoryPreflight:
    base = compile_memory_preflight(
        session=session,
        run_id=session.run_ids[0],
        source_sha=session.head_sha,
        policy_source_sha=session.policy_source_sha or "pol",
        trigger_context=_tc(),
    )
    if not required:
        return base.model_copy(
            update={
                "recursive_context_required": False,
                "invocation_reasons": [],
                "skip_reason": "deterministic_preflight_sufficient",
            }
        )
    return base.model_copy(
        update={
            "recursive_context_required": True,
            "invocation_reasons": ["graph_coverage_insufficient", "multiple_prior_root_causes"],
            "skip_reason": None,
            "missing_graph_edges": [f"gap:{i}" for i in range(THRESHOLD_MISSING_GRAPH_EDGES)],
            "rejected_hypotheses_from_prior_runs": ["H1: auth race", "H2: bad cache"],
            "citations": ["graph:blast_radius", "memory:run-old"],
        }
    )


def _session(state_env: Path, run_id: str):
    from agent_control.session import begin_typed_session

    return begin_typed_session(
        state_env,
        project="ai-sdlc-lab/demo-app",
        command_kind="review",
        run_id=run_id,
        head_sha=f"sha-{run_id}",
        trigger_context=_tc(),
        policy_source_sha=f"pol-{run_id}",
    )


def _run_preflight(state_env: Path, preflight: MemoryPreflight, *, backend: str):
    return run_conditional_recursive_context(
        preflight=preflight,
        question="Which hypothesis fits the CI evidence?",
        state_root=state_env,
        controller_backend=backend,
    )


def _run(state_env: Path, run_id: str, *, backend: str, required: bool = True):
    preflight = _qualifying_preflight(_session(state_env, run_id), required=required)
    return _run_preflight(state_env, preflight, backend=backend)


def test_yaml_default_is_deterministic(state_env: Path) -> None:
    assert resolve_controller_backend(settings=Settings()) == "deterministic"


def test_backend_precedence_override_then_env_then_yaml(
    state_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(BACKEND_ENV, "model")
    assert resolve_controller_backend(settings=Settings()) == "model"
    assert resolve_controller_backend(settings=Settings(), override="deterministic") == (
        "deterministic"
    )
    monkeypatch.setenv(BACKEND_ENV, "not-a-backend")
    assert resolve_controller_backend(settings=Settings()) == "deterministic"


def test_required_false_makes_no_model_call_even_under_c1(
    state_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spy = _patch_gateway(monkeypatch, _GatewaySpy())
    monkeypatch.setenv(BACKEND_ENV, "model")

    result = _run(state_env, "run-t005-skip", backend="model", required=False)

    assert result.schema_version == SCHEMA_VERSION
    assert result.recursive_context_required is False
    assert result.invoked is False
    assert result.skipped is True
    assert result.controller_backend == "model"
    assert result.controller_model_invoked is False
    assert spy.calls == []


def test_c0_arm_never_invokes_controller_model(
    state_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spy = _patch_gateway(monkeypatch, _GatewaySpy())

    result = _run(state_env, "run-t005-c0", backend="deterministic")

    assert result.invoked is True
    assert result.controller_backend == "deterministic"
    assert result.controller_model_invoked is False
    assert result.controller_mode == "fallback_deterministic"
    assert result.controller_model_id == ""
    assert result.controller_attempts == 0
    assert result.controller_prompt_tokens == 0
    assert spy.calls == []
    assert "call_primary_model" in {s.tool for s in result.subcalls}


def test_c1_arm_invokes_configured_2070_controller(
    state_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spy = _patch_gateway(monkeypatch, _GatewaySpy())

    result = _run(state_env, "run-t005-c1", backend="model")

    assert result.invoked is True
    assert result.controller_backend == "model"
    assert result.controller_model_invoked is True
    assert result.controller_mode == "model_2070"
    assert result.controller_model_id == "qwen2.5-coder:3b"
    assert result.controller_role == "summarizer"
    assert result.controller_role_label == "gpu-2070"
    assert result.controller_attempts == 1
    assert result.controller_prompt_tokens == 231
    assert result.controller_completion_tokens == 47
    assert result.controller_gpu_seconds == pytest.approx(1.5)
    assert result.controller_wall_seconds >= 0.0
    assert result.controller_data_left_homelab is False
    assert result.budget_used.input_tokens == 231
    assert result.budget_used.output_tokens == 47
    assert len(spy.calls) == 1
    assert spy.calls[0]["role"] == "summarizer"
    assert spy.calls[0]["project"] == "ai-sdlc-lab/demo-app"


def test_c1_prompt_carries_only_evidence_references(
    state_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spy = _patch_gateway(monkeypatch, _GatewaySpy())

    _run(state_env, "run-t005-prompt", backend="model")

    prompt = spy.calls[0]["user_prompt"]
    assert "graph:blast_radius" in prompt
    assert spy.calls[0]["max_tokens"] <= 1024
    assert "read-only context controller" in spy.calls[0]["system_prompt"]


def test_c0_and_c1_differ_only_by_backend(
    state_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_gateway(monkeypatch, _GatewaySpy())

    # Identical task input; the arm is the only difference.
    preflight = _qualifying_preflight(_session(state_env, "run-t005-ab"))
    c0 = _run_preflight(state_env, preflight, backend="deterministic")
    c1 = _run_preflight(state_env, preflight, backend="model")

    assert c0.question == c1.question
    assert c0.invocation_reasons == c1.invocation_reasons
    assert c0.recursive_context_required == c1.recursive_context_required is True
    assert c0.invoked == c1.invoked is True
    assert [s.tool for s in c0.subcalls] == [s.tool for s in c1.subcalls]
    assert c0.budget.model_dump() == c1.budget.model_dump()
    assert c0.budget_used.subcalls == c1.budget_used.subcalls
    assert (c0.controller_backend, c0.controller_model_invoked) == ("deterministic", False)
    assert (c1.controller_backend, c1.controller_model_invoked) == ("model", True)


def test_c1_model_failure_fails_soft_to_valid_result(
    state_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    down = _patch_gateway(monkeypatch, _GatewayDown())

    result = _run(state_env, "run-t005-c1-down", backend="model")

    assert RecursiveContextResult.model_validate(result.model_dump(mode="json"))
    assert result.schema_version == SCHEMA_VERSION
    assert result.invoked is True
    assert result.controller_backend == "model"
    assert result.controller_model_invoked is False
    assert result.controller_mode == "fallback_deterministic"
    assert result.controller_error_class == "ModelRouteExhausted"
    assert result.controller_attempts == 1
    assert down.calls == 1
    assert result.evidence_refs, "fail-soft result must still cite evidence"


def test_controller_stays_read_only_in_both_arms(
    state_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_gateway(monkeypatch, _GatewaySpy())

    for run_id, backend in (("run-t005-ro0", "deterministic"), ("run-t005-ro1", "model")):
        result = _run(state_env, run_id, backend=backend)
        assert result.allow_repo_write is False
        assert result.allow_network is False
        assert result.allow_secret_paths is False
        assert result.require_evidence_citations is True


def test_telemetry_payload_exposes_gate_g2_fields(
    state_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_gateway(monkeypatch, _GatewaySpy())

    payload = controller_telemetry_payload(_run(state_env, "run-t005-tel", backend="model"))

    for field in (
        "recursive_context_required",
        "recursive_context_invoked",
        "controller_backend",
        "controller_model_invoked",
        "controller_role",
        "controller_model_id",
        "invocation_reasons",
        "controller_prompt_tokens",
        "controller_completion_tokens",
        "controller_wall_seconds",
        "controller_gpu_seconds",
        "stop_reason",
    ):
        assert field in payload, field
    assert payload["controller_model_invoked"] is True
    assert payload["invocation_reasons"]


def test_prepare_dispatch_defaults_to_c0_and_records_telemetry(
    state_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    telemetry = _prepare_dispatch_event(state_env, monkeypatch, backend_env=None)
    assert telemetry["controller_backend"] == "deterministic"
    assert telemetry["controller_model_invoked"] is False


def test_prepare_dispatch_honours_c1_env_override(
    state_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    telemetry = _prepare_dispatch_event(state_env, monkeypatch, backend_env="model")
    assert telemetry["controller_backend"] == "model"
    assert telemetry["controller_model_invoked"] is True
    assert telemetry["controller_model_id"] == "qwen2.5-coder:3b"
    assert telemetry["recursive_context_required"] is True


# --- V10 Wave C: local-only trust boundary + timing truth ------------------


class _GatewayNoTimings(_GatewaySpy):
    """An endpoint that answers but reports no eval timings (OpenAI-compatible)."""

    def __call__(self, role: str, **kwargs: Any) -> dict[str, Any]:
        response = super().__call__(role, **kwargs)
        response["usage"] = {"prompt_tokens": 231, "completion_tokens": 47}
        return response


@pytest.mark.parametrize(
    "base_url,expected",
    [
        ("http://100.125.235.54:11434", True),
        ("http://192.168.4.62:11434", True),
        ("http://127.0.0.1:11434", True),
        ("http://msi.tail25fd47.ts.net:11434", True),
        ("http://control-plane:8080", True),
        ("https://api.openai.com/v1", False),
        ("https://api.anthropic.com", False),
        ("", False),
    ],
)
def test_endpoint_is_homelab_classifies_routes(base_url: str, expected: bool) -> None:
    from agent_control.recursive_context.model_client import endpoint_is_homelab

    assert endpoint_is_homelab(base_url) is expected


def test_c1_refuses_external_route_and_never_sends_the_request(
    state_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CT104-key scenario: 2070 down, external fallback allowed by policy."""
    monkeypatch.setenv("MODEL_2070_BASE_URL", "")
    monkeypatch.setenv("MODEL_2070_FALLBACK_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("MODEL_2070_FALLBACK_NAME", "gpt-4o-mini")
    monkeypatch.setenv("MODEL_2070_FALLBACK_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("MODEL_FALLBACK_ENABLED", "true")
    monkeypatch.setenv("REPO_EXTERNAL_MODEL_POLICY", "*")

    def _explode(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("the C1 controller must not reach an external provider")

    monkeypatch.setattr("agent_workers.rlm.completion.chat_completion", _explode)

    result = _run(state_env, "run-wavec-refuse", backend="model")

    assert result.controller_model_invoked is False
    assert result.controller_local_only_enforced is True
    assert result.controller_external_routes_refused == 1
    assert result.controller_error_class == "external_route_refused"
    assert result.controller_data_left_homelab is False
    assert result.controller_provider == ""
    assert result.controller_mode == "fallback_deterministic"
    assert result.evidence_refs, "refusal must still return a citable artifact"


def test_c1_missing_endpoint_timing_is_null_not_zero(
    state_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_gateway(monkeypatch, _GatewayNoTimings())

    result = _run(state_env, "run-wavec-no-timing", backend="model")

    assert result.controller_model_invoked is True
    assert result.controller_gpu_seconds is None
    assert "controller_gpu_seconds" in result.controller_missing_fields
    assert result.controller_prompt_tokens == 231
    assert "controller_prompt_tokens" not in result.controller_missing_fields


def test_c1_prefers_the_model_the_endpoint_says_it_served(
    state_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _WrongModelServed(_GatewaySpy):
        def __call__(self, role: str, **kwargs: Any) -> dict[str, Any]:
            response = super().__call__(role, **kwargs)
            response["model_reported"] = "llama3:8b"
            return response

    _patch_gateway(monkeypatch, _WrongModelServed())

    result = _run(state_env, "run-wavec-model-id", backend="model")

    assert result.controller_model_invoked is True
    assert result.controller_model_id == "llama3:8b"
    assert result.controller_model_id_source == "endpoint_reported"


def test_c1_flags_a_model_id_that_only_echoes_local_config(
    state_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_gateway(monkeypatch, _GatewaySpy())

    result = _run(state_env, "run-wavec-model-id-echo", backend="model")

    assert result.controller_model_id == "qwen2.5-coder:3b"
    assert result.controller_model_id_source == "configured"
    assert "controller_model_id" in result.controller_missing_fields


def test_failed_c1_marks_the_model_id_as_never_invoked(
    state_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_gateway(monkeypatch, _GatewayDown())

    result = _run(state_env, "run-wavec-model-id-down", backend="model")

    assert result.controller_model_invoked is False
    assert result.controller_model_id_source == "planned_not_invoked"


def test_c1_records_the_boundary_it_enforced(
    state_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_gateway(monkeypatch, _GatewaySpy())

    payload = controller_telemetry_payload(_run(state_env, "run-wavec-bound", backend="model"))

    assert payload["controller_local_only_enforced"] is True
    assert payload["controller_route_class"] == "direct_local"
    assert payload["controller_external_routes_refused"] == 0
    assert payload["controller_data_left_homelab"] is False


def test_local_only_guard_passes_homelab_and_blocks_external(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_control.model_router import ResolvedEndpoint
    from agent_control.recursive_context.model_client import (
        ControllerEgressRefused,
        ControllerTelemetry,
        _local_only_complete,
    )

    seen: list[str] = []

    def _fake_chat_completion(endpoint: Any, **_kwargs: Any) -> dict[str, Any]:
        seen.append(endpoint.base_url)
        return {"content": "ok"}

    monkeypatch.setattr("agent_workers.rlm.completion.chat_completion", _fake_chat_completion)
    telemetry = ControllerTelemetry()
    guard = _local_only_complete(telemetry)

    def _endpoint(provider: str, base_url: str, model: str) -> ResolvedEndpoint:
        return ResolvedEndpoint(
            role="summarizer",
            tier="2070",
            provider=provider,  # type: ignore[arg-type]
            base_url=base_url,
            model=model,
            api_key="",
            primary_provider="gpu",
        )

    assert guard(_endpoint("gpu", "http://100.125.235.54:11434", "qwen2.5-coder:3b")) == {
        "content": "ok"
    }
    with pytest.raises(ControllerEgressRefused):
        guard(_endpoint("fallback", "https://api.openai.com/v1", "gpt-4o-mini"))
    with pytest.raises(ControllerEgressRefused):
        # Provider label alone is not trusted; the host must also be homelab.
        guard(_endpoint("gpu", "https://api.openai.com/v1", "gpt-4o-mini"))

    assert seen == ["http://100.125.235.54:11434"]
    assert telemetry.external_routes_refused == 2
    assert telemetry.endpoint_base_url == "http://100.125.235.54:11434"


def _prepare_dispatch_event(
    state_env: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    backend_env: str | None,
) -> dict[str, Any]:
    from agent_control.events import load_project_events
    from agent_control.session import prepare_typed_rlm_dispatch
    from agent_control.workflows.dispatch import build_rlm_job
    from agent_shared.models.intent import CommandIntent
    from agent_shared.models.state import VerificationState

    _patch_gateway(monkeypatch, _GatewaySpy())
    if backend_env is not None:
        monkeypatch.setenv(BACKEND_ENV, backend_env)

    vs = VerificationState(
        project="ai-sdlc-lab/demo-app",
        command_intent=CommandIntent(
            activated=True,
            activation="/agent",
            kind="review",
            natural_language_task="",
            confidence=1.0,
        ),
        dispatch_recommended=True,
    )
    trigger = {
        "event_id": f"t005-{backend_env or 'default'}",
        "delivery_id": f"d-t005-{backend_env or 'default'}",
        "type": "gitea.issue_comment",
        "project": "ai-sdlc-lab/demo-app",
        "payload": {
            "comment": {"body": "/agent review", "id": 21, "user": {"login": "alice"}},
            "issue": {"number": 2},
        },
    }
    job = build_rlm_job(vs, trigger)
    assert job is not None

    real_compile = compile_memory_preflight

    def _force_required(**kwargs: Any) -> MemoryPreflight:
        return real_compile(**kwargs).model_copy(
            update={
                "recursive_context_required": True,
                "invocation_reasons": ["graph_coverage_insufficient"],
                "skip_reason": None,
                "citations": ["graph:blast_radius"],
            }
        )

    monkeypatch.setattr(
        "agent_control.session.prepare_dispatch.compile_memory_preflight",
        _force_required,
    )
    prepared = prepare_typed_rlm_dispatch(state_env, job)
    assert prepared.recursive_context_result is not None

    events = [
        ev
        for ev in load_project_events(state_env, "ai-sdlc-lab/demo-app")
        if ev.get("type") == "agent.recursive_context_completed"
    ]
    assert events, "recursive context completion must be observable"
    return events[-1]["payload"]
