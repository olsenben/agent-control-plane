"""Slice 5.6 verification evidence gate tests."""

from __future__ import annotations

from pathlib import Path

from agent_control.events import load_project_events
from agent_control.session import (
    SessionTerminalReason,
    begin_typed_session,
    handle_ingest_session_update,
    load_session,
)
from agent_control.session.verification import (
    apply_ci_verdict_to_session,
    load_verification_claim,
    request_session_verification,
)
from agent_shared.models.agent_session import SessionStatus
from agent_shared.models.events import AgentRunCompletedEvent
from agent_shared.models.jobs import TriggerContext


def _tc() -> TriggerContext:
    return TriggerContext(
        event_type="gitea.issue_comment",
        issue_number=2,
        author="alice",
        raw_body="/agent review",
        normalized_body="/agent review",
    )


def test_review_emits_verification_missing_before_finished(tmp_path: Path) -> None:
    state = tmp_path / "agent-state"
    state.mkdir()
    s = begin_typed_session(
        state,
        project="ai-sdlc-lab/demo-app",
        command_kind="review",
        run_id="run-rev56",
        head_sha="abc123",
        trigger_context=_tc(),
    )
    event = AgentRunCompletedEvent(
        run_id="run-rev56",
        job_id="j1",
        workflow_id="run-rev56",
        session_id=s.session_id,
        trigger_event_id="rev56",
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
    loaded = load_session(state, "ai-sdlc-lab/demo-app", s.session_id)
    assert loaded is not None
    assert loaded.status == SessionStatus.FINISHED
    assert loaded.terminal_reason_code == "ingest_completed"
    claim = load_verification_claim(state, "ai-sdlc-lab/demo-app", s.session_id)
    assert claim is not None
    assert claim.status == "missing"
    types = [e["type"] for e in load_project_events(state, "ai-sdlc-lab/demo-app")]
    assert "agent.verification_missing" in types
    assert types.index("agent.verification_missing") < types.index("agent.session_finished")


def test_publish_requests_verification_stays_running(tmp_path: Path) -> None:
    state = tmp_path / "agent-state"
    state.mkdir()
    s = begin_typed_session(
        state,
        project="ai-sdlc-lab/demo-app",
        command_kind="fix",
        run_id="run-fix56",
        head_sha="srcsha",
        trigger_context=TriggerContext(
            event_type="gitea.issue_comment",
            issue_number=2,
            author="alice",
            raw_body="/agent fix",
            normalized_body="/agent fix",
        ),
    )
    updated = request_session_verification(
        state,
        project="ai-sdlc-lab/demo-app",
        run_id="run-fix56",
        commit_sha="deadbeef" * 5,
    )
    assert updated is not None
    assert updated.status == SessionStatus.RUNNING
    claim = load_verification_claim(state, "ai-sdlc-lab/demo-app", s.session_id)
    assert claim is not None
    assert claim.status == "requested"
    assert claim.scope_commit_sha == "deadbeef" * 5
    events = load_project_events(state, "ai-sdlc-lab/demo-app")
    assert any(e["type"] == "agent.verification_requested" for e in events)
    assert not any(e["type"] == "agent.session_finished" for e in events)

    # Idempotent re-request
    request_session_verification(
        state,
        project="ai-sdlc-lab/demo-app",
        run_id="run-fix56",
        commit_sha="deadbeef" * 5,
    )
    assert (
        sum(
            1
            for e in load_project_events(state, "ai-sdlc-lab/demo-app")
            if e["type"] == "agent.verification_requested"
        )
        == 1
    )


def test_ci_verified_finishes_session(tmp_path: Path) -> None:
    state = tmp_path / "agent-state"
    state.mkdir()
    s = begin_typed_session(
        state,
        project="ai-sdlc-lab/demo-app",
        command_kind="fix",
        run_id="run-civ",
        head_sha="src",
        trigger_context=TriggerContext(
            event_type="gitea.issue_comment",
            issue_number=2,
            author="alice",
            raw_body="/agent fix",
            normalized_body="/agent fix",
        ),
    )
    sha = "aa" * 20
    request_session_verification(
        state, project="ai-sdlc-lab/demo-app", run_id="run-civ", commit_sha=sha
    )
    apply_ci_verdict_to_session(
        state,
        project="ai-sdlc-lab/demo-app",
        fix_run_id="run-civ",
        verdict="verified",
        previous_verdict="pending",
        expected_head_commit_sha=sha,
        verdict_revision=1,
    )
    loaded = load_session(state, "ai-sdlc-lab/demo-app", s.session_id)
    assert loaded is not None
    assert loaded.status == SessionStatus.FINISHED
    assert loaded.terminal_reason_code == SessionTerminalReason.CI_VERIFIED.value
    claim = load_verification_claim(state, "ai-sdlc-lab/demo-app", s.session_id)
    assert claim is not None
    assert claim.status == "passed"
    types = [e["type"] for e in load_project_events(state, "ai-sdlc-lab/demo-app")]
    assert "agent.verification_passed" in types
    assert "agent.session_finished" in types


def test_ci_failing_without_repair_fails_session(tmp_path: Path) -> None:
    state = tmp_path / "agent-state"
    state.mkdir()
    s = begin_typed_session(
        state,
        project="ai-sdlc-lab/demo-app",
        command_kind="fix",
        run_id="run-cif",
        head_sha="src",
        trigger_context=TriggerContext(
            event_type="gitea.issue_comment",
            issue_number=2,
            author="alice",
            raw_body="/agent fix",
            normalized_body="/agent fix",
        ),
    )
    sha = "bb" * 20
    request_session_verification(
        state, project="ai-sdlc-lab/demo-app", run_id="run-cif", commit_sha=sha
    )
    apply_ci_verdict_to_session(
        state,
        project="ai-sdlc-lab/demo-app",
        fix_run_id="run-cif",
        verdict="failing",
        previous_verdict="pending",
        expected_head_commit_sha=sha,
        verdict_revision=2,
        defer_fail_for_repair=False,
    )
    loaded = load_session(state, "ai-sdlc-lab/demo-app", s.session_id)
    assert loaded is not None
    assert loaded.status == SessionStatus.FAILED
    assert loaded.terminal_reason_code == "verification_failed"


def test_ci_failing_with_repair_stays_running(tmp_path: Path) -> None:
    state = tmp_path / "agent-state"
    state.mkdir()
    s = begin_typed_session(
        state,
        project="ai-sdlc-lab/demo-app",
        command_kind="fix",
        run_id="run-cir",
        head_sha="src",
        trigger_context=TriggerContext(
            event_type="gitea.issue_comment",
            issue_number=2,
            author="alice",
            raw_body="/agent fix",
            normalized_body="/agent fix",
        ),
    )
    sha = "cc" * 20
    request_session_verification(
        state, project="ai-sdlc-lab/demo-app", run_id="run-cir", commit_sha=sha
    )
    apply_ci_verdict_to_session(
        state,
        project="ai-sdlc-lab/demo-app",
        fix_run_id="run-cir",
        verdict="failing",
        previous_verdict="pending",
        expected_head_commit_sha=sha,
        verdict_revision=3,
        defer_fail_for_repair=True,
    )
    loaded = load_session(state, "ai-sdlc-lab/demo-app", s.session_id)
    assert loaded is not None
    assert loaded.status == SessionStatus.RUNNING
    claim = load_verification_claim(state, "ai-sdlc-lab/demo-app", s.session_id)
    assert claim is not None
    assert claim.status == "failed"
    assert any(
        e["type"] == "agent.verification_failed"
        for e in load_project_events(state, "ai-sdlc-lab/demo-app")
    )


def test_ci_expired_blocks_verification_missing(tmp_path: Path) -> None:
    state = tmp_path / "agent-state"
    state.mkdir()
    s = begin_typed_session(
        state,
        project="ai-sdlc-lab/demo-app",
        command_kind="fix",
        run_id="run-cie",
        head_sha="src",
        trigger_context=TriggerContext(
            event_type="gitea.issue_comment",
            issue_number=2,
            author="alice",
            raw_body="/agent fix",
            normalized_body="/agent fix",
        ),
    )
    sha = "dd" * 20
    request_session_verification(
        state, project="ai-sdlc-lab/demo-app", run_id="run-cie", commit_sha=sha
    )
    apply_ci_verdict_to_session(
        state,
        project="ai-sdlc-lab/demo-app",
        fix_run_id="run-cie",
        verdict="expired",
        previous_verdict="pending",
        expected_head_commit_sha=sha,
        verdict_revision=4,
    )
    loaded = load_session(state, "ai-sdlc-lab/demo-app", s.session_id)
    assert loaded is not None
    assert loaded.status == SessionStatus.BLOCKED
    assert loaded.terminal_reason_code == "verification_missing"
