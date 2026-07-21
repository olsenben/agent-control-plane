"""V7 T04 — bake-off memory namespace isolation."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_control.bakeoff_memory import (
    BakeoffMemoryError,
    BakeoffMemoryFacade,
    assert_writebacks_isolated,
    marker_record,
)
from agent_control.bakeoff_profiles import (
    PROFILE_IDS,
    run_all_profiles_against_bundle,
    run_profile_against_bundle,
)
from agent_control.eval_export import export_eval_bundle
from agent_control.observe.events import append_control_decision
from agent_control.session.storage import persist_session_with_run_index
from agent_shared.models.agent_session import AgentSession, SessionStatus


def _fixture_bundle(root: Path) -> Path:
    project = "ai-sdlc-lab/demo-app"
    run_id = "run-v7t04"
    session = AgentSession(
        session_id="sess-v7t04",
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
        summary="t04",
        session_id=session.session_id,
        run_id=run_id,
        trace_id=session.trace_id,
    )
    _, path = export_eval_bundle(root, project=project, run_id=run_id, output_dir=root / "exp")
    return path


def test_refuse_production_write_and_reset() -> None:
    facade = BakeoffMemoryFacade()
    rec = marker_record(run_id="r1", profile_id="A", namespace="production")
    with pytest.raises(BakeoffMemoryError, match="production"):
        facade.upsert("production", rec)
    with pytest.raises(BakeoffMemoryError, match="production"):
        facade.reset("production")
    with pytest.raises(BakeoffMemoryError, match="production"):
        facade.fork("production", "bakeoff/profile-A/x")
    assert facade.production_memory_touched is False


def test_refuse_non_bakeoff_namespace() -> None:
    facade = BakeoffMemoryFacade()
    rec = marker_record(run_id="r1", profile_id="A", namespace="eval_export")
    with pytest.raises(BakeoffMemoryError, match="bakeoff/"):
        facade.upsert("eval_export", rec)


def test_profiles_cannot_see_each_others_writebacks() -> None:
    facade = BakeoffMemoryFacade()
    ns_a = "bakeoff/profile-A/run-v7t04"
    ns_b = "bakeoff/profile-B/run-v7t04"
    facade.prepare_namespace(ns_a)
    facade.prepare_namespace(ns_b)
    facade.upsert(ns_a, marker_record(run_id="wb-a", profile_id="A", namespace=ns_a))
    facade.upsert(ns_b, marker_record(run_id="wb-b", profile_id="B", namespace=ns_b))
    assert facade.visible_run_ids(ns_a) == {"wb-a"}
    assert facade.visible_run_ids(ns_b) == {"wb-b"}
    assert_writebacks_isolated(facade, [ns_a, ns_b])


def test_fork_copies_then_reset_clears() -> None:
    facade = BakeoffMemoryFacade()
    seed = "bakeoff/seed/base"
    dest = "bakeoff/profile-C/run-v7t04"
    facade.reset(seed)
    facade.upsert(seed, marker_record(run_id="seed-1", profile_id="S", namespace=seed))
    copied = facade.fork(seed, dest)
    assert copied == 1
    assert facade.visible_run_ids(dest) == {"seed-1"}
    facade.reset(dest)
    assert facade.visible_run_ids(dest) == set()
    # Seed unchanged after dest reset.
    assert facade.visible_run_ids(seed) == {"seed-1"}


def test_empty_fork_from_eval_export_metadata() -> None:
    facade = BakeoffMemoryFacade()
    meta = facade.prepare_namespace("bakeoff/profile-A/r1", seed_namespace="eval_export")
    assert meta["seed_copied"] == 0
    assert meta["forked_from"] is None
    assert meta["record_count"] == 0
    assert facade.production_memory_touched is False


def test_prepare_refuses_production_seed() -> None:
    facade = BakeoffMemoryFacade()
    with pytest.raises(BakeoffMemoryError, match="production"):
        facade.prepare_namespace("bakeoff/profile-A/r1", seed_namespace="production")


def test_all_profiles_isolated_on_shared_facade(tmp_path: Path) -> None:
    bundle = _fixture_bundle(tmp_path)
    results = run_all_profiles_against_bundle(bundle, output_dir=tmp_path / "out")
    assert len(results) == 4
    namespaces = [doc["memory_namespace"] for doc, _ in results]
    assert len(set(namespaces)) == 4
    for doc, _ in results:
        isolation = doc["memory_isolation"]
        assert isolation["schema_version"] == "bakeoff_memory_isolation.v1"
        assert isolation["production_memory_touched"] is False
        assert doc["production_memory_touched"] is False
        assert isolation["record_count"] >= 1
        assert isolation["memory_namespace"].startswith("bakeoff/profile-")
        assert doc["profile_id"] in PROFILE_IDS


def test_single_profile_isolation_block(tmp_path: Path) -> None:
    bundle = _fixture_bundle(tmp_path)
    doc, _ = run_profile_against_bundle(bundle, "B", output_dir=tmp_path / "out")
    assert doc["memory_isolation"]["memory_namespace"] == doc["memory_namespace"]
    assert "bakeoff/profile-B/" in doc["memory_namespace"]
