"""T08 — bounded recursive Qwen loop (evidence-selected CI retries)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_control.qwen_loop.artifacts import load_qwen_loop_artifact, persist_qwen_loop_artifact
from agent_control.qwen_loop.evidence import select_evidence_context
from agent_control.qwen_loop.loop import assert_loop_terminates, evaluate_ci_grounded_retry
from agent_control.qwen_loop.observe_hook import record_ci_grounded_qwen_loop
from agent_control.session import begin_typed_session
from agent_shared.models.ci import EvidenceJobRecord, FailureEvidenceManifest
from agent_shared.models.jobs import TriggerContext
from agent_shared.models.qwen_loop import SCHEMA_VERSION, QwenLoopBudget
from agent_shared.models.recursive_context import RecursiveContextResult
from support.policy_pin import install_fake_policy_pin


def _tc() -> TriggerContext:
    return TriggerContext(
        event_type="gitea.issue_comment",
        issue_number=9,
        author="alice",
        raw_body="/agent fix",
        normalized_body="/agent fix",
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


def _evidence(*, status: str = "collected", failure_class: str = "lint_failure") -> FailureEvidenceManifest:
    return FailureEvidenceManifest(
        evidence_observation_id="obs-t08",
        status=status,  # type: ignore[arg-type]
        fix_run_id="run-t08",
        repository="ai-sdlc-lab/demo-app",
        expected_head_commit_sha="sha-t08",
        workflow_run_id="99",
        failure_class=failure_class,  # type: ignore[arg-type]
        has_terminal_failed_job=status == "collected",
        jobs=[
            EvidenceJobRecord(
                job_id="job-1",
                name="lint",
                status="completed",
                conclusion="failure",
            )
        ],
        collected_at="2026-07-20T00:00:00+00:00",
    )


def test_ci_fail_with_evidence_allows_bounded_retry() -> None:
    result = evaluate_ci_grounded_retry(
        session_id="sess-t08",
        run_id="run-t08",
        repo="ai-sdlc-lab/demo-app",
        ci_verdict="failing",
        completed_attempts=0,
        evidence=_evidence(),
        force_enabled=True,
    )
    assert result.schema_version == SCHEMA_VERSION
    assert result.action == "retry"
    assert result.bounded is True
    assert result.unbounded_forbidden is True
    assert result.attempt == 1
    assert result.max_attempts == 3
    assert result.selected_context.evidence_refs
    assert "ci_failure_evidence" in result.selected_context.selection_sources
    assert "does_not_enable_6f2_repair_allowlist" in result.notes


def test_budget_exhausted_stops_no_unbounded_loop() -> None:
    budget = QwenLoopBudget(max_ci_repair_iterations=2)
    results = assert_loop_terminates(max_attempts=2, has_evidence=True)
    assert results[-1].action == "stop"
    assert results[-1].stop_reason == "budget_exhausted"
    assert len(results) <= 3
    # Exactly max retries then stop
    retries = [r for r in results if r.action == "retry"]
    assert len(retries) == 2
    assert all(r.bounded and r.unbounded_forbidden for r in results)

    # Direct call past budget
    stopped = evaluate_ci_grounded_retry(
        session_id="sess-t08",
        run_id="run-t08",
        repo="ai-sdlc-lab/demo-app",
        ci_verdict="failing",
        completed_attempts=2,
        evidence=_evidence(),
        budget=budget,
        force_enabled=True,
    )
    assert stopped.action == "stop"
    assert stopped.stop_reason == "budget_exhausted"


def test_verified_stops_with_verification_passed() -> None:
    result = evaluate_ci_grounded_retry(
        session_id="sess-t08",
        run_id="run-t08",
        repo="ai-sdlc-lab/demo-app",
        ci_verdict="verified",
        completed_attempts=1,
        evidence=_evidence(),
        force_enabled=True,
    )
    assert result.action == "stop"
    assert result.stop_reason == "verification_passed"


def test_missing_evidence_stops_when_required() -> None:
    result = evaluate_ci_grounded_retry(
        session_id="sess-t08",
        run_id="run-t08",
        repo="ai-sdlc-lab/demo-app",
        ci_verdict="failing",
        completed_attempts=0,
        evidence=None,
        force_enabled=True,
    )
    assert result.action == "stop"
    assert result.stop_reason == "insufficient_evidence"


def test_evidence_selection_prefers_ci_then_recursive_context() -> None:
    rc = RecursiveContextResult(
        run_id="run-t08",
        repo="ai-sdlc-lab/demo-app",
        session_id="sess-t08",
        evidence_refs=["graph:caller:foo", "memory:run-old"],
        rejected_hypotheses=["H1: race"],
        artifact_digest="abc123",
        invoked=True,
    )
    ctx = select_evidence_context(evidence=_evidence(), recursive_context=rc)
    assert ctx.evidence_refs[0].startswith("ci_evidence:")
    assert "graph:caller:foo" in ctx.evidence_refs
    assert "H1: race" in ctx.rejected_hypotheses
    assert ctx.recursive_context_digest == "abc123"
    assert ctx.selection_sources == ["ci_failure_evidence", "recursive_context"]


def test_disabled_loop_stops() -> None:
    result = evaluate_ci_grounded_retry(
        session_id="sess-t08",
        run_id="run-t08",
        repo="ai-sdlc-lab/demo-app",
        ci_verdict="failing",
        evidence=_evidence(),
        force_enabled=False,
    )
    assert result.action == "stop"
    assert result.stop_reason == "disabled"


def test_persist_and_observe_hook(state_env: Path) -> None:
    session = begin_typed_session(
        state_env,
        project="ai-sdlc-lab/demo-app",
        command_kind="fix",
        run_id="run-t08-hook",
        head_sha="sha-hook",
        trigger_context=_tc(),
        policy_source_sha="pol-hook",
    )
    first = record_ci_grounded_qwen_loop(
        state_env,
        repository="ai-sdlc-lab/demo-app",
        fix_run_id="run-t08-hook",
        ci_verdict="failing",
        evidence=_evidence(),
    )
    assert first is not None
    assert first.action == "retry"
    loaded = load_qwen_loop_artifact(state_env, session.project, session.session_id)
    assert loaded is not None
    assert loaded.artifact_digest

    # Consume attempts until budget exhausted
    cur = first
    for _ in range(5):
        cur = record_ci_grounded_qwen_loop(
            state_env,
            repository="ai-sdlc-lab/demo-app",
            fix_run_id="run-t08-hook",
            ci_verdict="failing",
            evidence=_evidence(),
        )
        assert cur is not None
        if cur.action == "stop":
            break
    assert cur is not None
    assert cur.stop_reason == "budget_exhausted"
    assert cur.bounded is True

    stamped, ref, created = persist_qwen_loop_artifact(state_env, cur)
    assert stamped.artifact_digest
    assert ref.artifact_type == "qwen_loop_result"
    assert created is False
