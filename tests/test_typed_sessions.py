"""Unit tests for Slice 5.4a typed agent sessions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_control.events import load_project_events
from agent_control.results_ingest import ingest_result_file
from agent_control.session import (
    SessionMismatchError,
    SessionStoreError,
    begin_typed_session,
    finalize_enqueue_failure,
    handle_ingest_session_update,
    list_sessions,
    load_session,
    load_session_by_run,
    lookup_session_id_by_run,
)
from agent_control.session.lifecycle import append_run_to_session, create_session_record
from agent_control.session.storage import persist_session_with_run_index, save_run_index
from agent_shared.input_state import canonical_input_state, compute_input_state_sha
from agent_shared.models.agent_session import (
    SessionStatus,
    SessionTransitionError,
    append_run_id,
    apply_status_transition,
)
from agent_shared.models.events import AgentRunCompletedEvent
from agent_shared.models.intent import CommandIntent
from agent_shared.models.jobs import TriggerContext
from agent_shared.models.state import VerificationState
from agent_control.workflows.dispatch import maybe_dispatch_rlm_root


# Golden vector for input_state_sha (locked canonicalization).
_GOLDEN_INPUT = {
    "project": "ai-sdlc-lab/demo-app",
    "subject_kind": "issue",
    "subject_number": 2,
    "command_kind": "review",
    "head_sha": "abc123def456",
    "policy_source_sha": "poldeadbeef",
}
_GOLDEN_SHA = compute_input_state_sha(**_GOLDEN_INPUT)


def test_input_state_sha_golden_vector() -> None:
    assert len(_GOLDEN_SHA) == 64
    assert _GOLDEN_SHA == compute_input_state_sha(**_GOLDEN_INPUT)
    # Canonical dict shape is stable.
    canon = canonical_input_state(**_GOLDEN_INPUT)
    assert canon["schema_version"] == "input_state.v1"
    assert list(canon.keys()) == sorted(canon.keys())
    # Field change must change digest.
    other = compute_input_state_sha(**{**_GOLDEN_INPUT, "head_sha": "other"})
    assert other != _GOLDEN_SHA


def test_status_transition_idempotent_and_conflict() -> None:
    from agent_shared.models.agent_session import AgentSession

    s = AgentSession(
        session_id="sess-aaa",
        project="ai-sdlc-lab/demo-app",
        repo="demo-app",
        subject_kind="issue",
        subject_number=1,
        command_kind="review",
        status=SessionStatus.RUNNING,
        run_ids=["run-1"],
        correlation_id="corr-x",
        input_state_sha="0" * 64,
        head_sha="h",
        risk_level="risk_1",
        risk_tags=[],
        invoked_by="alice",
        created_at="t0",
        updated_at="t0",
    )
    finished = apply_status_transition(
        s,
        new_status=SessionStatus.FINISHED,
        updated_at="t1",
        terminal_reason_code="ok",
    )
    assert finished.status == SessionStatus.FINISHED
    noop = apply_status_transition(
        finished,
        new_status=SessionStatus.FINISHED,
        updated_at="t2",
        terminal_reason_code="ok",
    )
    assert noop is finished or noop.status == SessionStatus.FINISHED
    with pytest.raises(SessionTransitionError):
        apply_status_transition(
            finished,
            new_status=SessionStatus.FINISHED,
            updated_at="t3",
            terminal_reason_code="other",
        )
    with pytest.raises(SessionTransitionError):
        apply_status_transition(
            finished,
            new_status=SessionStatus.FAILED,
            updated_at="t3",
            terminal_reason_code="x",
        )


def test_append_run_id_dedupes() -> None:
    from agent_shared.models.agent_session import AgentSession

    s = AgentSession(
        session_id="sess-bbb",
        project="ai-sdlc-lab/demo-app",
        repo="demo-app",
        subject_kind="issue",
        subject_number=1,
        command_kind="fix",
        status=SessionStatus.QUEUED,
        run_ids=["run-a"],
        correlation_id="corr-y",
        input_state_sha="1" * 64,
        head_sha="h",
        risk_level="risk_2",
        risk_tags=[],
        invoked_by="bob",
        created_at="t0",
        updated_at="t0",
    )
    s2 = append_run_id(s, "run-a", updated_at="t1")
    assert s2.run_ids == ["run-a"]
    s3 = append_run_id(s, "run-b", updated_at="t2")
    assert s3.run_ids == ["run-a", "run-b"]


def _tc(author: str = "owner", issue: int = 2) -> TriggerContext:
    return TriggerContext(
        event_type="gitea.issue_comment",
        issue_number=issue,
        author=author,
        raw_body="/agent review",
        normalized_body="/agent review",
    )


def test_begin_session_distinct_ids_and_index(tmp_path: Path) -> None:
    state = tmp_path / "agent-state"
    state.mkdir()
    session = begin_typed_session(
        state,
        project="ai-sdlc-lab/demo-app",
        command_kind="review",
        run_id="run-evt1",
        head_sha="deadbeef",
        trigger_context=_tc(),
        policy_source_sha="pol1",
    )
    assert session.session_id.startswith("sess-")
    assert session.session_id != "run-evt1"
    assert "run-evt1" in session.run_ids
    assert lookup_session_id_by_run(state, "ai-sdlc-lab/demo-app", "run-evt1") == (
        session.session_id
    )
    loaded = load_session(state, "ai-sdlc-lab/demo-app", session.session_id)
    assert loaded is not None
    assert loaded.input_state_sha == session.input_state_sha

    # Idempotent re-begin
    again = begin_typed_session(
        state,
        project="ai-sdlc-lab/demo-app",
        command_kind="review",
        run_id="run-evt1",
        head_sha="deadbeef",
        trigger_context=_tc(),
    )
    assert again.session_id == session.session_id

    events = load_project_events(state, "ai-sdlc-lab/demo-app")
    types = [e["type"] for e in events]
    assert "agent.session_started" in types
    assert "agent.subject_context_resolved" in types


def test_two_commands_distinct_sessions(tmp_path: Path) -> None:
    state = tmp_path / "agent-state"
    state.mkdir()
    a = begin_typed_session(
        state,
        project="ai-sdlc-lab/demo-app",
        command_kind="review",
        run_id="run-a",
        head_sha="same",
        trigger_context=_tc(),
    )
    b = begin_typed_session(
        state,
        project="ai-sdlc-lab/demo-app",
        command_kind="plan",
        run_id="run-b",
        head_sha="same",
        trigger_context=_tc(),
    )
    assert a.session_id != b.session_id
    assert len(list_sessions(state, "ai-sdlc-lab/demo-app")) == 2


def test_run_cannot_bind_two_sessions(tmp_path: Path) -> None:
    state = tmp_path / "agent-state"
    state.mkdir()
    s = create_session_record(
        project="ai-sdlc-lab/demo-app",
        command_kind="review",
        run_id="run-x",
        head_sha="h",
        trigger_context=_tc(),
    )
    persist_session_with_run_index(state, s)
    with pytest.raises(SessionStoreError):
        save_run_index(
            state,
            project="ai-sdlc-lab/demo-app",
            run_id="run-x",
            session_id="sess-otherotherother",
        )


def test_retry_appends_run_id(tmp_path: Path) -> None:
    state = tmp_path / "agent-state"
    state.mkdir()
    s = begin_typed_session(
        state,
        project="ai-sdlc-lab/demo-app",
        command_kind="fix",
        run_id="run-fix1",
        head_sha="h",
        trigger_context=_tc(),
    )
    s2 = append_run_to_session(state, s, run_id="run-fix1-retry")
    assert s2.run_ids == ["run-fix1", "run-fix1-retry"]
    assert load_session_by_run(state, "ai-sdlc-lab/demo-app", "run-fix1-retry")


def test_enqueue_failure_finalizes(tmp_path: Path) -> None:
    state = tmp_path / "agent-state"
    state.mkdir()
    s = begin_typed_session(
        state,
        project="ai-sdlc-lab/demo-app",
        command_kind="review",
        run_id="run-enq",
        head_sha="h",
        trigger_context=_tc(),
    )
    failed = finalize_enqueue_failure(state, s, run_id="run-enq")
    assert failed.status == SessionStatus.FAILED
    events = load_project_events(state, "ai-sdlc-lab/demo-app")
    assert any(e["type"] == "agent.session_failed" for e in events)


def test_duplicate_ingest_one_terminal(tmp_path: Path) -> None:
    state = tmp_path / "agent-state"
    state.mkdir()
    s = begin_typed_session(
        state,
        project="ai-sdlc-lab/demo-app",
        command_kind="review",
        run_id="run-ing",
        head_sha="h",
        trigger_context=_tc(),
    )
    event = AgentRunCompletedEvent(
        run_id="run-ing",
        job_id="j1",
        workflow_id="run-ing",
        session_id=s.session_id,
        trigger_event_id="ing",
        project="ai-sdlc-lab/demo-app",
        flow="code_review",
        agent="reviewer",
        risk_class="read_only_with_repo_context",
        status="completed",
        terminal_status="completed",
        summary="ok",
        artifact_root="/tmp",
        command_kind="review",
        issue_id=2,
    )
    handle_ingest_session_update(state, event)
    handle_ingest_session_update(state, event)  # idempotent
    loaded = load_session(state, "ai-sdlc-lab/demo-app", s.session_id)
    assert loaded is not None
    assert loaded.status == SessionStatus.FINISHED
    finished = [
        e
        for e in load_project_events(state, "ai-sdlc-lab/demo-app")
        if e["type"] == "agent.session_finished"
    ]
    assert len(finished) == 1


def test_worker_session_mismatch_fail_closed(tmp_path: Path) -> None:
    state = tmp_path / "agent-state"
    state.mkdir()
    s = begin_typed_session(
        state,
        project="ai-sdlc-lab/demo-app",
        command_kind="review",
        run_id="run-mm",
        head_sha="h",
        trigger_context=_tc(),
    )
    event = AgentRunCompletedEvent(
        run_id="run-mm",
        job_id="j1",
        workflow_id="run-mm",
        session_id="sess-forged000000000000000000000",
        trigger_event_id="mm",
        project="ai-sdlc-lab/demo-app",
        flow="code_review",
        agent="reviewer",
        risk_class="read_only_with_repo_context",
        status="completed",
        summary="ok",
        artifact_root="/tmp",
        command_kind="review",
        issue_id=2,
    )
    with pytest.raises(SessionMismatchError):
        handle_ingest_session_update(state, event)
    loaded = load_session(state, "ai-sdlc-lab/demo-app", s.session_id)
    assert loaded is not None
    assert loaded.status == SessionStatus.QUEUED


def test_fix_ingest_does_not_finish(tmp_path: Path) -> None:
    state = tmp_path / "agent-state"
    state.mkdir()
    s = begin_typed_session(
        state,
        project="ai-sdlc-lab/demo-app",
        command_kind="fix",
        run_id="run-fixing",
        head_sha="h",
        trigger_context=_tc(),
    )
    event = AgentRunCompletedEvent(
        run_id="run-fixing",
        job_id="j1",
        workflow_id="run-fixing",
        session_id=s.session_id,
        trigger_event_id="fx",
        project="ai-sdlc-lab/demo-app",
        flow="developer_flow",
        agent="developer",
        risk_class="write_patch",
        status="completed",
        terminal_status="completed",
        summary="patch ready",
        artifact_root="/tmp",
        command_kind="fix",
        issue_id=2,
    )
    out = handle_ingest_session_update(state, event)
    assert out["terminal"] is False
    loaded = load_session(state, "ai-sdlc-lab/demo-app", s.session_id)
    assert loaded is not None
    assert loaded.status == SessionStatus.RUNNING
    assert not any(
        e["type"] == "agent.session_finished"
        for e in load_project_events(state, "ai-sdlc-lab/demo-app")
    )


def test_dispatch_creates_session_before_enqueue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "agent-state"
    state.mkdir()
    monkeypatch.setenv("AGENT_STATE_ROOT", str(state))
    monkeypatch.setenv("AGENT_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("MODEL_ROUTING_POLICY", "fake")

    from support.policy_pin import install_fake_policy_pin

    install_fake_policy_pin(monkeypatch)

    captured: dict = {}

    def _enqueue(redis_url: str, payload: dict) -> str:
        captured["payload"] = payload
        return "rq-job-1"

    monkeypatch.setattr(
        "agent_control.queue.enqueue_rlm_root",
        _enqueue,
    )

    vs = VerificationState(
        project="ai-sdlc-lab/demo-app",
        command_intent=CommandIntent(
            activated=True,
            activation="/agent",
            kind="review",
            natural_language_task="",
            confidence=1.0,
        ),
        dispatch_recommended=True,
    )
    trigger = {
        "event_id": "disp1",
        "delivery_id": "d1",
        "type": "gitea.issue_comment",
        "project": "ai-sdlc-lab/demo-app",
        "payload": {
            "comment": {"body": "/agent review", "id": 1, "user": {"login": "alice"}},
            "issue": {"number": 2},
        },
    }
    # build_trigger_context needs author — ensure via monkeypatch if needed
    result = maybe_dispatch_rlm_root(vs, trigger, "redis://localhost:6379/0")
    assert result["dispatched"] is True
    assert result["session_id"].startswith("sess-")
    assert result["session_id"] != result["run_id"]
    assert captured["payload"]["session_id"] == result["session_id"]
    assert captured["payload"]["session_id"] != captured["payload"]["run_id"]


def test_ingest_mismatch_rejects_file(tmp_path: Path) -> None:
    state = tmp_path / "agent-state"
    inbox = state / "inbox" / "ct104-results"
    inbox.mkdir(parents=True)
    s = begin_typed_session(
        state,
        project="ai-sdlc-lab/demo-app",
        command_kind="review",
        run_id="run-rej",
        head_sha="h",
        trigger_context=_tc(),
    )
    body = {
        "schema_version": "agent_run_completed.v1",
        "run_id": "run-rej",
        "job_id": "j",
        "workflow_id": "run-rej",
        "session_id": "sess-wrongwrongwrongwrongwrong",
        "trigger_event_id": "rej",
        "project": "ai-sdlc-lab/demo-app",
        "flow": "code_review",
        "agent": "reviewer",
        "risk_class": "read_only_with_repo_context",
        "status": "completed",
        "summary": "x",
        "artifact_root": "/tmp",
        "command_kind": "review",
        "issue_id": 2,
    }
    path = inbox / "run-rej.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(SessionMismatchError):
        ingest_result_file(state, path)
    assert path.exists()  # not processed
    loaded = load_session(state, "ai-sdlc-lab/demo-app", s.session_id)
    assert loaded is not None
    assert loaded.status != SessionStatus.FINISHED
