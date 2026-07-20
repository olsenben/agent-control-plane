"""T07 / 8c — conditional recursive context worker."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_control.memory.preflight import compile_memory_preflight
from agent_control.recursive_context.tools import ReadOnlyToolBelt, ToolBudget, ToolResult
from agent_control.recursive_context.worker import run_conditional_recursive_context
from agent_control.session import begin_typed_session, prepare_typed_rlm_dispatch
from agent_shared.models.intent import CommandIntent
from agent_shared.models.jobs import TriggerContext
from agent_shared.models.memory_preflight import (
    THRESHOLD_MISSING_GRAPH_EDGES,
    MemoryPreflight,
)
from agent_shared.models.recursive_context import SCHEMA_VERSION
from agent_shared.models.state import VerificationState
from support.policy_pin import install_fake_policy_pin


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
    install_fake_policy_pin(monkeypatch)
    return state


def _preflight(session, *, required: bool) -> MemoryPreflight:
    base = compile_memory_preflight(
        session=session,
        run_id=session.run_ids[0],
        source_sha=session.head_sha,
        policy_source_sha=session.policy_source_sha or "pol",
        trigger_context=_tc(),
    )
    if required:
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
    return base.model_copy(
        update={
            "recursive_context_required": False,
            "invocation_reasons": [],
            "skip_reason": "deterministic_preflight_sufficient",
        }
    )


def test_false_path_skips_2070(state_env: Path) -> None:
    session = begin_typed_session(
        state_env,
        project="ai-sdlc-lab/demo-app",
        command_kind="review",
        run_id="run-rc-skip",
        head_sha="sha-skip",
        trigger_context=_tc(),
        policy_source_sha="pol-skip",
    )
    pf = _preflight(session, required=False)
    called = {"model": False}

    def _model(q: str, refs: list[str]) -> ToolResult:
        called["model"] = True
        return ToolResult(tool="call_primary_model", ok=True, summary="nope", evidence_refs=refs)

    result = run_conditional_recursive_context(
        preflight=pf,
        question="why?",
        state_root=state_env,
        primary_model=_model,
    )
    assert result.schema_version == SCHEMA_VERSION
    assert result.skipped is True
    assert result.invoked is False
    assert result.stop_reason == "deterministic_preflight_sufficient"
    assert result.controller_mode == "skipped"
    assert called["model"] is False
    assert result.subcalls == []


def test_true_path_returns_result_v1(state_env: Path) -> None:
    session = begin_typed_session(
        state_env,
        project="ai-sdlc-lab/demo-app",
        command_kind="review",
        run_id="run-rc-true",
        head_sha="sha-true",
        trigger_context=_tc(),
        policy_source_sha="pol-true",
    )
    pf = _preflight(session, required=True)
    result = run_conditional_recursive_context(
        preflight=pf,
        question="Which hypothesis fits CI evidence?",
        state_root=state_env,
    )
    assert result.schema_version == SCHEMA_VERSION
    assert result.invoked is True
    assert result.skipped is False
    assert result.recursive_context_required is True
    assert result.evidence_refs, "must cite evidence"
    assert result.subcalls, "must run read-only tools"
    assert result.budget_used.subcalls >= 1
    assert result.allow_repo_write is False
    assert result.trajectory_relative_path
    traj = state_env / result.trajectory_relative_path
    assert traj.is_file()
    assert "call_primary_model" in {s.tool for s in result.subcalls}


def test_forbidden_tool_denied(state_env: Path) -> None:
    belt = ReadOnlyToolBelt(project="ai-sdlc-lab/demo-app")
    budget = ToolBudget(max_graph_queries=5, max_memory_records=5, max_subcalls=5)
    denied = belt.invoke("write_repo", {}, budget)
    assert denied.ok is False
    assert denied.summary == "policy_denied"


def test_compare_requires_evidence(state_env: Path) -> None:
    belt = ReadOnlyToolBelt(project="ai-sdlc-lab/demo-app")
    budget = ToolBudget(max_graph_queries=5, max_memory_records=5, max_subcalls=5)
    res = belt.invoke("compare_hypotheses", {"h1": "a", "h2": "b"}, budget)
    assert res.ok is False
    assert "evidence" in res.error


def test_budget_exhaustion(state_env: Path) -> None:
    session = begin_typed_session(
        state_env,
        project="ai-sdlc-lab/demo-app",
        command_kind="plan",
        run_id="run-rc-budget",
        head_sha="sha-b",
        trigger_context=_tc(),
        policy_source_sha="pol-b",
    )
    pf = _preflight(session, required=True)
    from agent_shared.models.recursive_context import RecursiveContextBudget

    # Pass budget explicitly — more reliable than patching budget_from_config.
    result = run_conditional_recursive_context(
        preflight=pf,
        state_root=state_env,
        budget=RecursiveContextBudget(max_subcalls=1, max_graph_queries=1, max_depth=1),
    )
    assert result.invoked is True
    assert result.budget_used.subcalls <= 1
    assert result.budget_used.tool_calls <= 1
    assert result.stop_reason == "budget_exhausted"


def test_prepare_skips_import_when_not_required(
    state_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys

    from agent_control.workflows.dispatch import build_rlm_job

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
        "event_id": "rc-no2070",
        "delivery_id": "d-rc",
        "type": "gitea.issue_comment",
        "project": "ai-sdlc-lab/demo-app",
        "payload": {
            "comment": {"body": "/agent review", "id": 9, "user": {"login": "alice"}},
            "issue": {"number": 2},
        },
    }
    job = build_rlm_job(vs, trigger)
    assert job is not None
    # Drop any prior imports from other tests
    for name in list(sys.modules):
        if "recursive_context" in name:
            del sys.modules[name]

    prepared = prepare_typed_rlm_dispatch(state_env, job)
    assert prepared.preflight.recursive_context_required is False
    assert prepared.recursive_context_result is None
    banned = [n for n in sys.modules if "recursive_context" in n]
    assert banned == []


def test_prepare_invokes_when_required(
    state_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agent_control.workflows.dispatch import build_rlm_job

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
        "event_id": "rc-yes",
        "delivery_id": "d-yes",
        "type": "gitea.issue_comment",
        "project": "ai-sdlc-lab/demo-app",
        "payload": {
            "comment": {"body": "/agent review", "id": 11, "user": {"login": "alice"}},
            "issue": {"number": 2},
        },
    }
    job = build_rlm_job(vs, trigger)
    assert job is not None

    real_compile = compile_memory_preflight

    def _force_required(**kwargs):
        pf = real_compile(**kwargs)
        return pf.model_copy(
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
    assert prepared.preflight.recursive_context_required is True
    assert prepared.recursive_context_result is not None
    assert prepared.recursive_context_result.schema_version == SCHEMA_VERSION
    assert prepared.recursive_context_result.invoked is True
    assert prepared.job.recursive_context_digest
    assert prepared.session.recursive_context is not None
