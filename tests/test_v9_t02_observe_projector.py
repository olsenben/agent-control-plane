"""V9 T02 -- observe.sqlite projection: fail-open (H7), identity (H3),
canonical AgentSession mirror (H6), display-safe payloads (T01 reuse),
rebuild, and the CLI entrypoint.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from agent_control.cli import main
from agent_control.config import Settings
from agent_control.events import AgentEvent, append_event, deterministic_event_id
from agent_control.observe import projector as projector_mod
from agent_control.observe.rebuild import rebuild_observe_db
from agent_control.observe.store import ObserveStore, observe_db_path
from agent_control.session import finalize_session, load_session
from agent_control.session.lifecycle import begin_typed_session
from agent_shared.models.jobs import TriggerContext

PROJECT = "ai-sdlc-lab/demo-app"


def _tc(issue_number: int = 7) -> TriggerContext:
    return TriggerContext(
        event_type="gitea.issue_comment",
        issue_number=issue_number,
        author="alice",
        raw_body="/agent review",
        normalized_body="/agent review",
    )


def _begin_session(state_root: Path, run_id: str = "run-t02"):
    return begin_typed_session(
        state_root,
        project=PROJECT,
        command_kind="review",
        run_id=run_id,
        head_sha="abc123",
        trigger_context=_tc(),
    )


# --- H3: identity + projection into observe.sqlite from real ledger appends ---


def test_begin_typed_session_projects_rows_into_observe_sqlite(tmp_path: Path) -> None:
    state_root = tmp_path / "agent-state"
    state_root.mkdir()
    session = _begin_session(state_root)

    store = ObserveStore(observe_db_path(state_root))
    rows = store.list_events_for_run(session.run_ids[0])
    event_types = {r["event_type"] for r in rows}
    assert "agent.session_started" in event_types
    assert "agent.subject_context_resolved" in event_types
    for row in rows:
        assert row["known_type"] == 1
        assert row["source_kind"] == "ct103"


def test_project_ledger_event_replay_is_idempotent(tmp_path: Path) -> None:
    """H3: replaying the exact same raw ledger event dict must not duplicate rows."""
    state_root = tmp_path / "agent-state"
    state_root.mkdir()
    store = ObserveStore(observe_db_path(state_root))
    raw_event = {
        "event_id": deterministic_event_id("ct103", "delivery-replay", "agent.session_started"),
        "type": "agent.session_started",
        "source": "ct103",
        "ledger_sequence": 1,
        "recorded_at": "2026-07-22T00:00:00+00:00",
        "payload": {"run_id": "run-replay", "session_id": "sess-replay"},
    }

    first = projector_mod.project_ledger_event(store, raw_event, project=PROJECT, state_root=state_root)
    second = projector_mod.project_ledger_event(store, raw_event, project=PROJECT, state_root=state_root)
    assert first == 1
    assert second is None
    assert store.count_events_for_run("run-replay") == 1


def test_events_without_run_id_are_skipped_not_errors(tmp_path: Path) -> None:
    state_root = tmp_path / "agent-state"
    state_root.mkdir()
    event = AgentEvent(
        event_id=deterministic_event_id("ct103", "delivery-1", "human.approval_granted"),
        type="human.approval_granted",
        raw_event_type="human.approval_granted",
        source="ct103",
        delivery_id="delivery-1",
        project=PROJECT,
        payload={"issue_id": 7, "approval_target_id": "fix-1"},
    )
    path, created = append_event(state_root, event)
    assert created is True
    assert path.is_file()

    db_path = observe_db_path(state_root)
    # No run_id in payload -- out of scope for the run/session-scoped
    # projection; the store must not even be opened for this event.
    assert not db_path.exists()


# --- T01 reuse: display-safe payloads, never raw secrets ---


def test_projected_event_never_stores_poisoned_payload_value(tmp_path: Path) -> None:
    state_root = tmp_path / "agent-state"
    state_root.mkdir()
    secret = "SECRET-BOT-TOKEN-VALUE"
    event = AgentEvent(
        event_id=deterministic_event_id("ct103", "delivery-poison", "agent.session_started"),
        type="agent.session_started",
        raw_event_type="agent.session_started",
        source="ct103",
        delivery_id="delivery-poison",
        project=PROJECT,
        payload={
            "schema_version": "agent_session_event.v1",
            "session_id": "sess-poison",
            "run_id": "run-poison",
            "repo": "demo-app",
            "project": PROJECT,
            "subject_kind": "issue",
            "subject_number": 7,
            "command_kind": "review",
            "risk_level": "low",
            "risk_tags": [],
            "input_state_sha": "sha",
            "head_sha": "sha",
            "correlation_id": "corr-1",
            "session_created_at": "2026-07-22T00:00:00+00:00",
            "event_at": "2026-07-22T00:00:00+00:00",
            "status": "queued",
            "invoked_by": "alice",
            # producer bug: a credential field that must never reach storage.
            "gitea_bot_token": secret,
        },
    )
    append_event(state_root, event)

    store = ObserveStore(observe_db_path(state_root))
    rows = store.list_events_for_run("run-poison")
    assert len(rows) == 1
    stored_json = rows[0]["observe_event_json"]
    assert secret not in stored_json
    parsed = json.loads(stored_json)
    assert "gitea_bot_token" in parsed["prohibited_field_names"]
    assert "gitea_bot_token" not in parsed["display_fields"]


# --- H6: canonical AgentSession mirror ---


def test_session_observation_mirrors_current_session_and_redacts_terminal_reason(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "agent-state"
    state_root.mkdir()
    session = _begin_session(state_root)
    run_id = session.run_ids[0]

    store = ObserveStore(observe_db_path(state_root))
    snapshot = store.get_session_observation(session.session_id)
    assert snapshot is not None
    assert snapshot["status"] == "queued"

    finalize_session(
        state_root,
        session,
        run_id=run_id,
        status="failed",
        reason_code="worker_failed",
        reason="Traceback: exception with secret-looking internal detail",
    )

    refreshed = store.get_session_observation(session.session_id)
    assert refreshed is not None
    assert refreshed["status"] == "failed"
    assert refreshed["terminal_reason_redacted"] == 1
    assert "Traceback" not in refreshed["session_json"]
    assert "secret-looking" not in refreshed["session_json"]

    loaded = load_session(state_root, PROJECT, session.session_id)
    assert loaded is not None
    assert loaded.terminal_reason is not None  # durable session file keeps the real reason


# --- H7: fail-open -- append_event must succeed even if observe.sqlite is broken ---


def test_append_event_succeeds_even_when_observe_store_raises(tmp_path: Path, monkeypatch) -> None:
    state_root = tmp_path / "agent-state"
    state_root.mkdir()

    def _boom(*args, **kwargs):
        raise RuntimeError("observe.sqlite is on fire")

    monkeypatch.setattr(projector_mod.ObserveStore, "insert_event", _boom)

    session = _begin_session(state_root)
    assert session.status.value == "queued"

    loaded = load_session(state_root, PROJECT, session.session_id)
    assert loaded is not None
    assert loaded.session_id == session.session_id


def test_fail_open_hook_never_raises_past_append_event(tmp_path: Path, monkeypatch) -> None:
    state_root = tmp_path / "agent-state"
    state_root.mkdir()

    def _boom(state_root_arg, event_dict, *, project):
        raise RuntimeError("projector exploded")

    monkeypatch.setattr(projector_mod, "project_event_fail_open", _boom)

    event = AgentEvent(
        event_id=deterministic_event_id("ct103", "delivery-fail-open", "agent.session_started"),
        type="agent.session_started",
        raw_event_type="agent.session_started",
        source="ct103",
        delivery_id="delivery-fail-open",
        project=PROJECT,
        payload={"run_id": "run-fail-open", "session_id": "sess-fail-open"},
    )
    path, created = append_event(state_root, event)
    assert created is True
    assert path.is_file()


# --- rebuild ---


def test_rebuild_reproduces_live_projection_counts(tmp_path: Path) -> None:
    state_root = tmp_path / "agent-state"
    state_root.mkdir()
    session = _begin_session(state_root)
    run_id = session.run_ids[0]
    finalize_session(
        state_root,
        session,
        run_id=run_id,
        status="finished",
        reason_code="ingest_completed",
        reason="ok",
    )

    store = ObserveStore(observe_db_path(state_root))
    live_count = store.count_events_for_run(run_id)
    assert live_count > 0

    result = rebuild_observe_db(state_root, PROJECT)
    assert result.events_projected == live_count
    assert result.size_warning is None

    rebuilt_count = store.count_events_for_run(run_id)
    assert rebuilt_count == live_count

    # Idempotent: rebuilding again yields the same counts, not duplicates.
    result2 = rebuild_observe_db(state_root, PROJECT)
    assert result2.events_projected == live_count


def test_rebuild_scoped_to_project_leaves_other_projects_untouched(tmp_path: Path) -> None:
    state_root = tmp_path / "agent-state"
    state_root.mkdir()
    session_a = _begin_session(state_root, run_id="run-proj-a")

    other_event = AgentEvent(
        event_id=deterministic_event_id("ct103", "delivery-other", "agent.session_started"),
        type="agent.session_started",
        raw_event_type="agent.session_started",
        source="ct103",
        delivery_id="delivery-other",
        project="ai-sdlc-lab/other-app",
        payload={"run_id": "run-other", "session_id": "sess-other"},
    )
    append_event(state_root, other_event)

    store = ObserveStore(observe_db_path(state_root))
    other_before = store.count_events_for_run("run-other")
    assert other_before == 1

    rebuild_observe_db(state_root, PROJECT)

    assert store.count_events_for_run("run-other") == other_before
    assert store.count_events_for_run(session_a.run_ids[0]) >= 1


# --- CLI ---


def test_cli_observe_rebuild_reports_counts(tmp_path: Path, monkeypatch) -> None:
    state_root = tmp_path / "agent-state"
    state_root.mkdir()
    monkeypatch.setenv("AGENT_STATE_ROOT", str(state_root))
    _begin_session(state_root)

    runner = CliRunner()
    result = runner.invoke(main, ["observe", "rebuild", "--repo", PROJECT])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["project"] == PROJECT
    assert data["events_projected"] >= 2
    assert data["size_warning"] is None


def test_settings_observe_db_path_and_size_warning_bytes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("OBSERVE_SQLITE_SIZE_WARNING_MB", "1")
    settings = Settings()
    assert settings.observe_db_path == tmp_path / "state" / "observe" / "observe.sqlite"
    assert settings.observe_sqlite_size_warning_bytes == 1 * 1024 * 1024
