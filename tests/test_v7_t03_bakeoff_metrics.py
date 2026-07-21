"""V7 T03 bake-off metrics."""

from __future__ import annotations

from pathlib import Path

from agent_control.bakeoff_metrics import (
    METRIC_FIELDS,
    build_metrics_for_bundle_file,
    extract_metrics_from_bundle,
)
from agent_control.bakeoff_profiles import run_profile_against_bundle
from agent_control.eval_export import export_eval_bundle
from agent_control.observe.events import append_control_decision
from agent_control.session.storage import persist_session_with_run_index
from agent_shared.models.agent_session import AgentSession, SessionStatus
from agent_shared.models.eval_bundle import EvalBundle


def _seed_bundle(root: Path, *, rich: bool = False) -> Path:
    project = "ai-sdlc-lab/demo-app"
    run_id = "run-v7t03"
    session = AgentSession(
        session_id="sess-v7t03",
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
    if rich:
        append_control_decision(
            root,
            project=project,
            kind="other",
            summary="repair iter 1 ci_repair",
            session_id=session.session_id,
            run_id=run_id,
            trace_id=session.trace_id,
        )
        append_control_decision(
            root,
            project=project,
            kind="model_fallback_selected",
            summary="model fallback",
            session_id=session.session_id,
            run_id=run_id,
            trace_id=session.trace_id,
        )
        append_control_decision(
            root,
            project=project,
            kind="policy_denied",
            summary="blocked",
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


def test_metric_field_contract() -> None:
    bundle = EvalBundle(
        manifest={"run_id": "r", "project": "a/b"},
        timeline=[],
        stages=[],
        eval_bundle_sha256="abc",
        memory_namespace="eval_export",
        production_memory_touched=False,
    )
    metrics = extract_metrics_from_bundle(bundle)
    assert metrics["schema_version"] == "bakeoff_metrics.v1"
    for field in METRIC_FIELDS:
        assert field in metrics
    assert metrics["evidence"]["production_memory_touched"] is False


def test_rich_timeline_metrics(tmp_path: Path) -> None:
    path = _seed_bundle(tmp_path, rich=True)
    metrics = build_metrics_for_bundle_file(path)
    assert metrics["repair_iterations"] >= 1
    assert metrics["fallback_count"] >= 1
    assert metrics["policy_violations"] >= 1
    assert metrics["ct102_verified_success"] is True


def test_bakeoff_run_embeds_metrics(tmp_path: Path) -> None:
    path = _seed_bundle(tmp_path, rich=True)
    doc, out = run_profile_against_bundle(path, "B", output_dir=tmp_path / "out")
    assert out.is_file()
    assert doc["metrics"]["schema_version"] == "bakeoff_metrics.v1"
    assert "repair_iterations" in doc["metrics"]
    assert Path(doc["metrics_path"]).is_file()
