"""V6 T08 eval bundle export."""

from __future__ import annotations

from pathlib import Path

from agent_control.eval_export import build_eval_bundle, export_eval_bundle, verify_eval_bundle_sha256
from agent_control.observe.events import append_control_decision
from agent_control.session.storage import persist_session_with_run_index
from agent_shared.models.agent_session import AgentSession, SessionStatus


def _seed_session(root: Path, project: str, run_id: str) -> None:
    session = AgentSession(
        session_id="sess-eval01",
        project=project,
        repo=project.split("/", 1)[1],
        subject_kind="issue",
        subject_number=1,
        command_kind="plan",
        status=SessionStatus.QUEUED,
        run_ids=[run_id],
        correlation_id="corr-eval01",
        trace_id="tr-eval01",
        input_state_sha="e" * 64,
        head_sha="f" * 40,
        policy_source_sha="a" * 40,
        risk_level="risk1",
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


def test_eval_bundle_content_addressed(tmp_path: Path) -> None:
    project = "ai-sdlc-lab/demo-app"
    run_id = "run-eval01"
    _seed_session(tmp_path, project, run_id)
    bundle = build_eval_bundle(tmp_path, project=project, run_id=run_id)
    assert bundle.schema_version == "eval_bundle.v1"
    assert bundle.eval_bundle_sha256
    assert verify_eval_bundle_sha256(bundle)
    assert bundle.production_memory_touched is False
    assert any(e.get("type") == "agent.control_decision" for e in bundle.timeline)


def test_export_writes_file_without_memory_touch(tmp_path: Path) -> None:
    project = "ai-sdlc-lab/demo-app"
    run_id = "run-eval02"
    _seed_session(tmp_path, project, run_id)
    out = tmp_path / "exports"
    bundle, path = export_eval_bundle(tmp_path, project=project, run_id=run_id, output_dir=out)
    assert path.is_file()
    assert bundle.eval_bundle_sha256[:12] in path.name
    assert verify_eval_bundle_sha256(bundle)
    # No writes under projects/.../memory
    memory_dirs = list((tmp_path / "projects").rglob("memory"))
    assert memory_dirs == [] or all(not p.is_dir() or not any(p.iterdir()) for p in memory_dirs)
