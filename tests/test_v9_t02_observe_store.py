"""V9 T02 -- observe.sqlite store: identity/sequence (H3), pagination, size warning.

Unit-level coverage of ObserveStore in isolation from the ledger/projector.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_control.observe.store import (
    DEFAULT_SIZE_WARNING_BYTES,
    ObserveStore,
    evaluate_size_warning,
    observe_db_path,
)


def _store(tmp_path: Path) -> ObserveStore:
    return ObserveStore(tmp_path / "observe" / "observe.sqlite")


def _insert(
    store: ObserveStore,
    *,
    run_id: str = "run-1",
    session_id: str | None = "sess-1",
    source_event_id: str = "evt-1",
    event_type: str = "agent.session_started",
    source_kind: str = "ct103",
) -> int | None:
    return store.insert_event(
        project="ai-sdlc-lab/demo-app",
        run_id=run_id,
        session_id=session_id,
        source_kind=source_kind,
        source_event_id=source_event_id,
        event_type=event_type,
        known_type=True,
        ledger_sequence=1,
        recorded_at="2026-07-22T00:00:00+00:00",
        observe_event_json=json.dumps({"type": event_type, "summary": "x"}),
    )


def test_observe_db_path_matches_memory_graph_convention(tmp_path: Path) -> None:
    assert observe_db_path(tmp_path) == tmp_path / "observe" / "observe.sqlite"


def test_insert_event_assigns_sequential_projection_sequence(tmp_path: Path) -> None:
    store = _store(tmp_path)
    seq1 = _insert(store, source_event_id="evt-1")
    seq2 = _insert(store, source_event_id="evt-2")
    seq3 = _insert(store, source_event_id="evt-3")
    assert (seq1, seq2, seq3) == (1, 2, 3)


def test_insert_event_idempotent_on_identity(tmp_path: Path) -> None:
    """H3: UNIQUE(run_id, source_kind, source_event_id) -- replay is a no-op."""
    store = _store(tmp_path)
    first = _insert(store, source_event_id="evt-dup")
    second = _insert(store, source_event_id="evt-dup")
    assert first == 1
    assert second is None
    rows = store.list_events_for_run("run-1")
    assert len(rows) == 1


def test_projection_sequence_scoped_per_run(tmp_path: Path) -> None:
    """H3: UNIQUE(run_id, projection_sequence) -- sequence resets per run_id."""
    store = _store(tmp_path)
    seq_a1 = _insert(store, run_id="run-a", source_event_id="a-1")
    seq_b1 = _insert(store, run_id="run-b", source_event_id="b-1")
    seq_a2 = _insert(store, run_id="run-a", source_event_id="a-2")
    assert (seq_a1, seq_b1, seq_a2) == (1, 1, 2)


def test_list_events_for_run_keyset_pagination(tmp_path: Path) -> None:
    store = _store(tmp_path)
    for i in range(5):
        _insert(store, source_event_id=f"evt-{i}")

    page1 = store.list_events_for_run("run-1", after_sequence=0, limit=2)
    assert [r["projection_sequence"] for r in page1] == [1, 2]

    page2 = store.list_events_for_run("run-1", after_sequence=page1[-1]["projection_sequence"], limit=2)
    assert [r["projection_sequence"] for r in page2] == [3, 4]

    page3 = store.list_events_for_run("run-1", after_sequence=page2[-1]["projection_sequence"], limit=2)
    assert [r["projection_sequence"] for r in page3] == [5]


def test_list_events_for_session_filters_by_session_id(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _insert(store, session_id="sess-a", source_event_id="a-1")
    _insert(store, session_id="sess-b", source_event_id="b-1")
    _insert(store, session_id="sess-a", source_event_id="a-2")

    rows = store.list_events_for_session("sess-a")
    assert {r["source_event_id"] for r in rows} == {"a-1", "a-2"}


def test_count_events_for_run(tmp_path: Path) -> None:
    store = _store(tmp_path)
    for i in range(3):
        _insert(store, source_event_id=f"evt-{i}")
    assert store.count_events_for_run("run-1") == 3
    assert store.count_events_for_run("run-missing") == 0


def test_delete_project_events_scoped_to_project(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.insert_event(
        project="ai-sdlc-lab/demo-app",
        run_id="run-1",
        session_id="sess-1",
        source_kind="ct103",
        source_event_id="evt-1",
        event_type="agent.session_started",
        known_type=True,
        ledger_sequence=1,
        recorded_at=None,
        observe_event_json="{}",
    )
    store.insert_event(
        project="ai-sdlc-lab/other-app",
        run_id="run-2",
        session_id="sess-2",
        source_kind="ct103",
        source_event_id="evt-2",
        event_type="agent.session_started",
        known_type=True,
        ledger_sequence=1,
        recorded_at=None,
        observe_event_json="{}",
    )
    store.delete_project_events("ai-sdlc-lab/demo-app")
    assert store.count_events_for_run("run-1") == 0
    assert store.count_events_for_run("run-2") == 1


def test_session_observation_upsert_and_get(tmp_path: Path) -> None:
    store = _store(tmp_path)
    row = {
        "session_id": "sess-1",
        "project": "ai-sdlc-lab/demo-app",
        "repo": "demo-app",
        "run_ids_json": json.dumps(["run-1"]),
        "subject_kind": "issue",
        "subject_number": 2,
        "command_kind": "review",
        "status": "queued",
        "trace_id": "trace-1",
        "correlation_id": "corr-1",
        "risk_level": "low",
        "risk_tags_json": json.dumps([]),
        "invoked_by": "alice",
        "acting_identity": "agent-bot",
        "created_at": "2026-07-22T00:00:00+00:00",
        "updated_at": "2026-07-22T00:00:00+00:00",
        "finished_at": None,
        "terminal_reason_code": None,
        "terminal_reason_redacted": 0,
        "session_json": json.dumps({"session_id": "sess-1"}),
    }
    store.upsert_session_observation(row, projection_sequence=1)
    fetched = store.get_session_observation("sess-1")
    assert fetched is not None
    assert fetched["status"] == "queued"
    assert fetched["last_projection_sequence"] == 1

    row["status"] = "running"
    store.upsert_session_observation(row, projection_sequence=2)
    fetched2 = store.get_session_observation("sess-1")
    assert fetched2 is not None
    assert fetched2["status"] == "running"
    assert fetched2["last_projection_sequence"] == 2


def test_session_observation_last_projection_sequence_monotonic(tmp_path: Path) -> None:
    """An out-of-order refresh must not regress the recorded sequence watermark."""
    store = _store(tmp_path)
    row = {
        "session_id": "sess-1",
        "project": "ai-sdlc-lab/demo-app",
        "repo": "demo-app",
        "run_ids_json": "[]",
        "subject_kind": "issue",
        "subject_number": 2,
        "command_kind": "review",
        "status": "running",
        "trace_id": None,
        "correlation_id": None,
        "risk_level": "low",
        "risk_tags_json": "[]",
        "invoked_by": "alice",
        "acting_identity": "agent-bot",
        "created_at": "2026-07-22T00:00:00+00:00",
        "updated_at": "2026-07-22T00:00:00+00:00",
        "finished_at": None,
        "terminal_reason_code": None,
        "terminal_reason_redacted": 0,
        "session_json": "{}",
    }
    store.upsert_session_observation(row, projection_sequence=5)
    store.upsert_session_observation(row, projection_sequence=2)
    fetched = store.get_session_observation("sess-1")
    assert fetched is not None
    assert fetched["last_projection_sequence"] == 5


@pytest.mark.parametrize(
    ("size_bytes", "threshold", "expect_warning"),
    [
        (100, 1000, False),
        (1000, 1000, False),
        (1001, 1000, True),
    ],
)
def test_evaluate_size_warning(size_bytes: int, threshold: int, expect_warning: bool) -> None:
    warning = evaluate_size_warning(size_bytes, threshold_bytes=threshold)
    assert (warning is not None) == expect_warning


def test_store_size_warning_reflects_actual_file(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _insert(store)
    # Tiny DB, well under default threshold.
    assert store.size_warning() is None
    assert store.size_warning(threshold_bytes=1) is not None


def test_default_size_warning_threshold_is_homelab_scale() -> None:
    assert DEFAULT_SIZE_WARNING_BYTES == 512 * 1024 * 1024
