"""V7 T02 bake-off profiles A–D."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_control.bakeoff_profiles import (
    PROFILE_IDS,
    BakeoffProfileError,
    get_profile,
    load_bakeoff_profiles,
    run_all_profiles_against_bundle,
    run_profile_against_bundle,
)
from agent_control.eval_export import export_eval_bundle
from agent_control.observe.events import append_control_decision
from agent_control.session.storage import persist_session_with_run_index
from agent_shared.models.agent_session import AgentSession, SessionStatus


def _fixture_bundle(root: Path) -> Path:
    project = "ai-sdlc-lab/demo-app"
    run_id = "run-v7t02"
    session = AgentSession(
        session_id="sess-v7t02",
        project=project,
        repo="demo-app",
        subject_kind="issue",
        subject_number=1,
        command_kind="plan",
        status=SessionStatus.QUEUED,
        run_ids=[run_id],
        correlation_id="c",
        trace_id="t",
        input_state_sha="a" * 64,
        head_sha="b" * 40,
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
        summary="t02",
        session_id=session.session_id,
        run_id=run_id,
        trace_id=session.trace_id,
    )
    _, path = export_eval_bundle(root, project=project, run_id=run_id, output_dir=root / "exp")
    return path


def test_load_four_profiles() -> None:
    profiles = load_bakeoff_profiles()
    assert set(profiles) == set(PROFILE_IDS)
    assert profiles["A"].recursive_context_enabled is False
    assert profiles["B"].recursive_context_enabled is True
    assert profiles["C"].max_graph_queries > profiles["B"].max_graph_queries
    assert profiles["D"].experimental is True
    for p in profiles.values():
        assert p.unbounded_recursion is False
        assert p.allow_repo_write is False
        assert p.injection_shadow_is_authority is False


def test_unknown_profile_fails() -> None:
    with pytest.raises(BakeoffProfileError):
        get_profile("Z")


def test_all_profiles_same_fixture(tmp_path: Path) -> None:
    bundle = _fixture_bundle(tmp_path)
    results = run_all_profiles_against_bundle(bundle, output_dir=tmp_path / "out")
    assert len(results) == 4
    digests = {doc["source_eval_bundle_sha256"] for doc, _ in results}
    assert len(digests) == 1
    namespaces = {doc["memory_namespace"] for doc, _ in results}
    assert len(namespaces) == 4
    for doc, path in results:
        assert path.is_file()
        assert doc["schema_version"] == "bakeoff_run.v1"
        assert doc["production_memory_touched"] is False
        assert doc["mode"] == "dry_run"
        assert doc["profile_id"] in PROFILE_IDS
        assert "bakeoff/profile-" in doc["memory_namespace"]


def test_single_profile_run(tmp_path: Path) -> None:
    bundle = _fixture_bundle(tmp_path)
    doc, path = run_profile_against_bundle(bundle, "A", output_dir=tmp_path / "out")
    assert doc["profile_id"] == "A"
    assert doc["recursive_context_enabled"] is False
    assert path.is_file()
