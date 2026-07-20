"""T06 / 8b — preflight consumes Orbit graph coverage + missing_edges."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_control.graph.snapshot import snapshot_project
from agent_control.memory.preflight import (
    compile_memory_preflight,
    decide_recursive_context,
)
from agent_control.session import begin_typed_session
from agent_shared.models.jobs import TriggerContext
from agent_shared.models.memory_preflight import (
    COMPILER_VERSION,
    THRESHOLD_MISSING_GRAPH_EDGES,
)
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


def test_decide_recursive_uses_missing_edges_threshold() -> None:
    required, reasons, skip = decide_recursive_context(
        prior_memory_count=0,
        distinct_prior_root_causes=0,
        missing_graph_edge_count=THRESHOLD_MISSING_GRAPH_EDGES,
    )
    assert required is True
    assert "graph_coverage_insufficient" in reasons
    assert skip == ""


def test_preflight_includes_orbit_coverage_when_indexed(
    state_env: Path, control_plane_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agent_control.config import Settings

    settings = Settings()
    snapshot_project(
        "ai-sdlc-lab/agent-control-plane",
        settings=settings,
        local_path=control_plane_root,
    )
    session = begin_typed_session(
        state_env,
        project="ai-sdlc-lab/agent-control-plane",
        command_kind="review",
        run_id="run-pf-8b-cov",
        head_sha="sha-8b",
        trigger_context=_tc(),
        policy_source_sha="pol-8b",
    )
    preflight = compile_memory_preflight(
        session=session,
        run_id="run-pf-8b-cov",
        source_sha="sha-8b",
        policy_source_sha="pol-8b",
        trigger_context=_tc(),
        settings=settings,
        changed_files=["src/agent_control/workflows/dispatch.py"],
    )
    assert preflight.compiler_version == COMPILER_VERSION
    assert COMPILER_VERSION.endswith("/8b")
    assert "graph:coverage" in preflight.citations
    assert "graph:blast_radius" in preflight.citations
    cov = preflight.graph_coverage
    assert isinstance(cov.get("edge_kinds"), dict)
    assert cov.get("edge_count", 0) > 0
    assert cov.get("files_indexed", 0) > 0
    assert "provenance_counts" in cov
    assert any(q.get("query_kind") == "coverage" for q in preflight.graph_queries)
    assert preflight.heuristic_inputs.missing_graph_edge_count == len(
        preflight.missing_graph_edges
    )


def test_preflight_merges_coverage_gaps_into_missing_edges(
    state_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agent_shared.models.review import BlastRadiusContext

    session = begin_typed_session(
        state_env,
        project="ai-sdlc-lab/demo-app",
        command_kind="review",
        run_id="run-pf-8b-miss",
        head_sha="sha-miss",
        trigger_context=_tc(),
        policy_source_sha="pol-miss",
    )

    monkeypatch.setattr(
        "agent_control.memory.preflight.compute_blast_radius",
        lambda *a, **k: BlastRadiusContext(missing_graph_edges=["blast:file_missing"]),
    )
    monkeypatch.setattr(
        "agent_control.memory.preflight.export_coverage_json",
        lambda *a, **k: {
            "edge_count": 0,
            "files_indexed": 0,
            "files_skipped": 0,
            "edge_kinds": {},
            "provenance_counts": {},
            "extractor_version": "orbit-8a.1",
            "source_sha": "",
            "confidence": "low",
            "missing_graph_edges": [
                "graph snapshot not found for repo",
                "coverage_gap:run_used_memory",
            ],
        },
    )
    preflight = compile_memory_preflight(
        session=session,
        run_id="run-pf-8b-miss",
        source_sha="sha-miss",
        policy_source_sha="pol-miss",
        trigger_context=_tc(),
    )
    assert "blast:file_missing" in preflight.missing_graph_edges
    assert "graph snapshot not found for repo" in preflight.missing_graph_edges
    assert "coverage_gap:run_used_memory" in preflight.missing_graph_edges
    assert preflight.graph_coverage["missing_graph_edges"] == len(preflight.missing_graph_edges)
    assert preflight.heuristic_inputs.missing_graph_edge_count == len(
        preflight.missing_graph_edges
    )


def test_preflight_heuristic_fires_on_merged_missing_edges(
    state_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agent_shared.models.review import BlastRadiusContext

    session = begin_typed_session(
        state_env,
        project="ai-sdlc-lab/demo-app",
        command_kind="plan",
        run_id="run-pf-8b-heur",
        head_sha="sha-heur",
        trigger_context=_tc(),
        policy_source_sha="pol-heur",
    )
    many = [f"coverage_gap:kind_{i}" for i in range(THRESHOLD_MISSING_GRAPH_EDGES)]
    monkeypatch.setattr(
        "agent_control.memory.preflight.compute_blast_radius",
        lambda *a, **k: BlastRadiusContext(missing_graph_edges=[]),
    )
    monkeypatch.setattr(
        "agent_control.memory.preflight.export_coverage_json",
        lambda *a, **k: {
            "edge_count": 1,
            "files_indexed": 1,
            "files_skipped": 0,
            "edge_kinds": {"repo_contains_file": 1},
            "provenance_counts": {"static_analysis": 1},
            "extractor_version": "orbit-8a.1",
            "source_sha": "abc",
            "confidence": "low",
            "missing_graph_edges": many,
        },
    )
    preflight = compile_memory_preflight(
        session=session,
        run_id="run-pf-8b-heur",
        source_sha="sha-heur",
        policy_source_sha="pol-heur",
        trigger_context=_tc(),
    )
    assert preflight.recursive_context_required is True
    assert "graph_coverage_insufficient" in preflight.invocation_reasons
    assert preflight.heuristic_inputs.missing_graph_edge_count >= THRESHOLD_MISSING_GRAPH_EDGES


def test_preflight_coverage_failure_is_fail_soft(
    state_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agent_shared.models.review import BlastRadiusContext

    session = begin_typed_session(
        state_env,
        project="ai-sdlc-lab/demo-app",
        command_kind="review",
        run_id="run-pf-8b-soft",
        head_sha="sha-soft",
        trigger_context=_tc(),
        policy_source_sha="pol-soft",
    )
    monkeypatch.setattr(
        "agent_control.memory.preflight.compute_blast_radius",
        lambda *a, **k: BlastRadiusContext(affected_services=["svc"]),
    )

    def _boom(*_a, **_k):
        raise RuntimeError("coverage store locked")

    monkeypatch.setattr("agent_control.memory.preflight.export_coverage_json", _boom)
    preflight = compile_memory_preflight(
        session=session,
        run_id="run-pf-8b-soft",
        source_sha="sha-soft",
        policy_source_sha="pol-soft",
        trigger_context=_tc(),
    )
    assert "graph_coverage_unavailable" in preflight.uncertainty
    assert "graph_coverage" in preflight.component_errors
    # Blast still succeeded — not a hard graph unavailable.
    assert preflight.component_results.graph in ("complete", "truncated")
    assert "graph:blast_radius" in preflight.citations
