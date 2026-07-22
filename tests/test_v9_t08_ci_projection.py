"""V9 T08 -- CT102 CI channel projection into observe.sqlite + Observatory
current-state phase.

Covers:
- Real ``agent.fix_ci_*`` ledger events (via
  :mod:`agent_control.ci.events`) land in ``observe.sqlite`` keyed by the
  underlying fix/repair session's ``run_id`` (H3 identity), with
  ``session_id`` resolved even though the raw payload never carries one.
- Late/duplicate CI verdicts never regress a terminal ``AgentSession``
  state, nor the Observatory's canonical current-state CI phase.
- ``ui.current_state_view``'s additive ``ci_phase`` panel.
"""

from __future__ import annotations

from pathlib import Path

from agent_control.ci.events import append_fix_ci_observed, append_fix_ci_verdict_changed
from agent_control.observe.ci_channel import current_ci_phase_view
from agent_control.observe.store import ObserveStore, observe_db_path
from agent_control.observe.ui import current_state_view
from agent_control.session.lifecycle import begin_typed_session
from agent_control.session.storage import load_session
from agent_control.session.verification import (
    apply_ci_verdict_to_session,
    request_session_verification,
)
from agent_shared.models.agent_session import SessionStatus
from agent_shared.models.ci import FixCiObservedEvent, FixCiVerdictChangedEvent, WorkflowObservation
from agent_shared.models.jobs import TriggerContext

PROJECT = "ai-sdlc-lab/demo-app"


def _tc() -> TriggerContext:
    return TriggerContext(
        event_type="gitea.issue_comment",
        issue_number=9,
        author="alice",
        raw_body="/agent fix",
        normalized_body="/agent fix",
    )


def _begin_fix_session(state_root: Path, run_id: str, head_sha: str):
    return begin_typed_session(
        state_root,
        project=PROJECT,
        command_kind="fix",
        run_id=run_id,
        head_sha=head_sha,
        trigger_context=_tc(),
    )


# --- H3 identity: fix_ci_* projects under the fix session's run_id ---


def test_fix_ci_observed_projects_under_fix_run_id_with_session_resolved(tmp_path: Path) -> None:
    state_root = tmp_path / "agent-state"
    state_root.mkdir()
    session = _begin_fix_session(state_root, "run-t08a", "a" * 40)

    append_fix_ci_observed(
        state_root,
        FixCiObservedEvent(
            fix_run_id="run-t08a",
            repository=PROJECT,
            expected_head_commit_sha="a" * 40,
            observation=WorkflowObservation(
                workflow_run_id="9001",
                status="completed",
                conclusion="success",
                head_sha="a" * 40,
            ),
            delivery_id="delivery-1",
        ),
    )

    store = ObserveStore(observe_db_path(state_root))
    rows = store.list_events_for_run("run-t08a")
    ci_rows = [r for r in rows if r["event_type"] == "agent.fix_ci_observed"]
    assert len(ci_rows) == 1
    assert ci_rows[0]["session_id"] == session.session_id
    assert ci_rows[0]["known_type"] == 1

    snapshot = store.get_session_observation(session.session_id)
    assert snapshot is not None  # H6 refresh fired even though the raw
    # fix_ci_observed payload never carries session_id.


def test_fix_ci_observed_replay_is_idempotent(tmp_path: Path) -> None:
    state_root = tmp_path / "agent-state"
    state_root.mkdir()
    _begin_fix_session(state_root, "run-t08b", "a" * 40)

    body = FixCiObservedEvent(
        fix_run_id="run-t08b",
        repository=PROJECT,
        expected_head_commit_sha="a" * 40,
        observation=WorkflowObservation(
            workflow_run_id="9002",
            status="completed",
            conclusion="success",
            head_sha="a" * 40,
        ),
        delivery_id="delivery-2",
    )
    append_fix_ci_observed(state_root, body)
    append_fix_ci_observed(state_root, body)  # same delivery -- idempotent ledger append

    store = ObserveStore(observe_db_path(state_root))
    rows = [r for r in store.list_events_for_run("run-t08b") if r["event_type"] == "agent.fix_ci_observed"]
    assert len(rows) == 1


def test_fix_ci_verdict_changed_projects_and_is_categorized_ci(tmp_path: Path) -> None:
    state_root = tmp_path / "agent-state"
    state_root.mkdir()
    _begin_fix_session(state_root, "run-t08c", "a" * 40)

    append_fix_ci_verdict_changed(
        state_root,
        FixCiVerdictChangedEvent(
            fix_run_id="run-t08c",
            repository=PROJECT,
            expected_head_commit_sha="a" * 40,
            previous_verdict="pending",
            verdict="verified",
            verdict_revision=1,
        ),
    )

    store = ObserveStore(observe_db_path(state_root))
    rows = store.list_events_for_run("run-t08c")
    verdict_rows = [r for r in rows if r["event_type"] == "agent.fix_ci_verdict_changed"]
    assert len(verdict_rows) == 1
    import json

    parsed = json.loads(verdict_rows[0]["observe_event_json"])
    assert parsed["category"] == "ci"
    assert parsed["known_type"] is True


# --- goal: late/duplicate CI verdict must NOT regress terminal AgentSession state ---


def test_late_duplicate_verdict_does_not_regress_terminal_session_or_ci_phase(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "agent-state"
    state_root.mkdir()
    session = _begin_fix_session(state_root, "run-t08d", "a" * 40)
    sha = "a" * 40

    request_session_verification(state_root, project=PROJECT, run_id="run-t08d", commit_sha=sha)

    # Terminal verdict lands first.
    apply_ci_verdict_to_session(
        state_root,
        project=PROJECT,
        fix_run_id="run-t08d",
        verdict="verified",
        previous_verdict="pending",
        expected_head_commit_sha=sha,
        verdict_revision=2,
    )
    loaded = load_session(state_root, PROJECT, session.session_id)
    assert loaded is not None
    assert loaded.status == SessionStatus.FINISHED

    phase_before = current_ci_phase_view(state_root, project=PROJECT, session_id=session.session_id)
    assert phase_before is not None
    assert phase_before["phase"] == "verified"

    # A late/duplicate "failing" verdict for an *older* revision arrives
    # after the session already went terminal (out-of-order delivery,
    # retry, or a superseded webhook redelivery).
    apply_ci_verdict_to_session(
        state_root,
        project=PROJECT,
        fix_run_id="run-t08d",
        verdict="failing",
        previous_verdict="pending",
        expected_head_commit_sha=sha,
        verdict_revision=1,
    )

    reloaded = load_session(state_root, PROJECT, session.session_id)
    assert reloaded is not None
    assert reloaded.status == SessionStatus.FINISHED, "terminal session status must not regress"

    phase_after = current_ci_phase_view(state_root, project=PROJECT, session_id=session.session_id)
    assert phase_after is not None
    assert phase_after["phase"] == "verified", "CI phase must not regress past a terminal verdict"
    assert phase_after == phase_before


def test_exact_duplicate_verdict_revision_is_a_pure_noop(tmp_path: Path) -> None:
    """Re-delivering the exact same terminal verdict/revision changes nothing."""
    state_root = tmp_path / "agent-state"
    state_root.mkdir()
    session = _begin_fix_session(state_root, "run-t08e", "b" * 40)
    sha = "b" * 40
    request_session_verification(state_root, project=PROJECT, run_id="run-t08e", commit_sha=sha)
    apply_ci_verdict_to_session(
        state_root,
        project=PROJECT,
        fix_run_id="run-t08e",
        verdict="verified",
        previous_verdict="pending",
        expected_head_commit_sha=sha,
        verdict_revision=1,
    )
    apply_ci_verdict_to_session(
        state_root,
        project=PROJECT,
        fix_run_id="run-t08e",
        verdict="verified",
        previous_verdict="verified",
        expected_head_commit_sha=sha,
        verdict_revision=1,
    )
    reloaded = load_session(state_root, PROJECT, session.session_id)
    assert reloaded is not None
    assert reloaded.status == SessionStatus.FINISHED


# --- current_state_view (ui.py): additive, backward-compatible ci_phase panel ---


def test_current_state_view_without_state_root_omits_ci_phase(tmp_path: Path) -> None:
    state_root = tmp_path / "agent-state"
    state_root.mkdir()
    session = _begin_fix_session(state_root, "run-t08f", "c" * 40)
    store = ObserveStore(observe_db_path(state_root))

    view = current_state_view(session, store)
    assert view["ci_phase"] is None


def test_current_state_view_with_state_root_surfaces_ci_phase(tmp_path: Path) -> None:
    state_root = tmp_path / "agent-state"
    state_root.mkdir()
    session = _begin_fix_session(state_root, "run-t08g", "d" * 40)
    sha = "d" * 40
    request_session_verification(state_root, project=PROJECT, run_id="run-t08g", commit_sha=sha)
    store = ObserveStore(observe_db_path(state_root))

    view = current_state_view(session, store, state_root=state_root)
    assert view["ci_phase"] is not None
    assert view["ci_phase"]["phase"] == "verifying"
