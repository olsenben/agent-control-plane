"""V7 T05 bake-off report."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from agent_control.bakeoff_profiles import run_all_profiles_against_bundle
from agent_control.bakeoff_report import (
    REPORT_SCHEMA,
    BakeoffReportError,
    assert_production_gates,
    build_bakeoff_report,
    build_negative_transfer_notes,
    emit_bakeoff_report_for_bundle,
)
from agent_control.eval_export import export_eval_bundle
from agent_control.observe.events import append_control_decision
from agent_control.session.storage import persist_session_with_run_index
from agent_shared.models.agent_session import AgentSession, SessionStatus


def _fixture_bundle(root: Path) -> Path:
    project = "ai-sdlc-lab/demo-app"
    run_id = "run-v7t05"
    session = AgentSession(
        session_id="sess-v7t05",
        project=project,
        repo="demo-app",
        subject_kind="issue",
        subject_number=1,
        command_kind="fix",
        status=SessionStatus.QUEUED,
        run_ids=[run_id],
        correlation_id="c",
        trace_id="t",
        input_state_sha="a" * 64,
        head_sha="b" * 40,
        risk_level="risk2",
        invoked_by="alice",
        created_at="2026-07-21T00:00:00+00:00",
        updated_at="2026-07-21T00:00:00+00:00",
    )
    persist_session_with_run_index(root, session)
    append_control_decision(
        root,
        project=project,
        kind="other",
        summary="seed",
        session_id=session.session_id,
        run_id=run_id,
        trace_id=session.trace_id,
    )
    append_control_decision(
        root,
        project=project,
        kind="ci_verdict_accepted",
        summary="ci passed ct102 verified",
        session_id=session.session_id,
        run_id=run_id,
        trace_id=session.trace_id,
    )
    _, path = export_eval_bundle(root, project=project, run_id=run_id, output_dir=root / "exp")
    return path


def test_emit_report_compares_a_to_d(tmp_path: Path) -> None:
    bundle = _fixture_bundle(tmp_path)
    report, path, results = emit_bakeoff_report_for_bundle(
        bundle, output_dir=tmp_path / "report"
    )
    assert path.is_file()
    assert report["schema_version"] == REPORT_SCHEMA
    assert report["profiles_compared"] == ["A", "B", "C", "D"]
    assert len(report["longitudinal"]) == 4
    assert report["dry_run_metric_parity"] is True
    assert report["production_gates"]["unbounded_recursion"] is False
    assert report["production_gates"]["injection_shadow_is_authority"] is False
    assert report["production_gates"]["all_passed"] is True
    assert report["production_memory_touched"] is False
    assert report["negative_transfer_detected"] is False
    kinds = {n["kind"] for n in report["negative_transfer_notes"]}
    assert "dry_run_parity" in kinds
    assert "promotion_rule" in kinds
    assert "memory_isolation" in kinds
    assert len(results) == 4


def test_production_gates_refuse_unbounded() -> None:
    bad = {
        "profile_id": "B",
        "unbounded_recursion": True,
        "injection_shadow_is_authority": False,
        "production_memory_touched": False,
        "memory_namespace": "bakeoff/profile-B/run",
        "memory_isolation": {"production_memory_touched": False},
    }
    with pytest.raises(BakeoffReportError, match="unbounded_recursion"):
        assert_production_gates(bad)


def test_production_gates_refuse_shadow_authority() -> None:
    bad = {
        "profile_id": "B",
        "unbounded_recursion": False,
        "injection_shadow_is_authority": True,
        "production_memory_touched": False,
        "memory_namespace": "bakeoff/profile-B/run",
        "memory_isolation": {"production_memory_touched": False},
    }
    with pytest.raises(BakeoffReportError, match="shadow"):
        assert_production_gates(bad)


def test_negative_transfer_when_metrics_regress() -> None:
    rows = [
        {
            "profile_id": "A",
            "experimental": False,
            "metrics": {
                "ct102_verified_success": True,
                "repair_iterations": 0,
                "fallback_count": 0,
                "policy_violations": 0,
                "tokens_input": 10,
                "tokens_output": 10,
                "cost_usd": 0.01,
                "wall_seconds": 1.0,
            },
        },
        {
            "profile_id": "B",
            "experimental": False,
            "metrics": {
                "ct102_verified_success": False,
                "repair_iterations": 3,
                "fallback_count": 1,
                "policy_violations": 1,
                "tokens_input": 100,
                "tokens_output": 100,
                "cost_usd": 1.0,
                "wall_seconds": 30.0,
            },
        },
        {
            "profile_id": "C",
            "experimental": False,
            "metrics": {
                "ct102_verified_success": True,
                "repair_iterations": 0,
                "fallback_count": 0,
                "policy_violations": 0,
                "tokens_input": 10,
                "tokens_output": 10,
                "cost_usd": 0.01,
                "wall_seconds": 1.0,
            },
        },
        {
            "profile_id": "D",
            "experimental": True,
            "metrics": {
                "ct102_verified_success": True,
                "repair_iterations": 0,
                "fallback_count": 0,
                "policy_violations": 0,
                "tokens_input": 10,
                "tokens_output": 10,
                "cost_usd": 0.01,
                "wall_seconds": 1.0,
            },
        },
    ]
    notes = build_negative_transfer_notes(rows, dry_run_parity=False)
    vs_b = next(n for n in notes if n.get("profile_id") == "B")
    assert vs_b["negative_transfer"] is True
    assert vs_b["promotion_blocked"] is True
    vs_d = next(n for n in notes if n.get("profile_id") == "D")
    assert vs_d["severity"] is True  # experimental


def test_build_report_from_runs_rejects_prod_touch(tmp_path: Path) -> None:
    bundle = _fixture_bundle(tmp_path)
    results = run_all_profiles_against_bundle(bundle, output_dir=tmp_path / "out")
    docs = [deepcopy(doc) for doc, _ in results]
    docs[0]["production_memory_touched"] = True
    with pytest.raises(BakeoffReportError, match="production memory"):
        build_bakeoff_report(docs)
