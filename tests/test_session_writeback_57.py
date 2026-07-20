"""Slice 5.7 — selective writeback from typed session trace."""

from __future__ import annotations

import json
from pathlib import Path

from agent_control.config import Settings
from agent_control.events import load_project_events
from agent_control.memory.store import MemoryStore
from agent_control.results_ingest import ingest_result_file
from agent_control.session import begin_typed_session, handle_ingest_session_update, load_session
from agent_shared.models.agent_session import SessionStatus
from agent_shared.models.events import AgentRunCompletedEvent
from agent_shared.models.jobs import TriggerContext
from agent_shared.models.memory import ADMISSION_POLICY_VERSION_57
from agent_shared.models.review import ReviewFinding, ReviewResult


def _tc() -> TriggerContext:
    return TriggerContext(
        event_type="gitea.issue_comment",
        issue_number=2,
        author="alice",
        raw_body="/agent review",
        normalized_body="/agent review",
    )


def _review_event(session_id: str, run_id: str = "run-wb57") -> AgentRunCompletedEvent:
    review = ReviewResult(
        findings=[ReviewFinding(id="F-57", summary="session-trace finding")],
        files_inspected=["README.md"],
        risk_tags=["prompt_injection"],
        confidence="medium",
        recommended_next_command="plan",
    )
    return AgentRunCompletedEvent(
        run_id=run_id,
        job_id=f"rlm-root-{run_id}",
        workflow_id=run_id,
        session_id=session_id,
        trigger_event_id=run_id.replace("run-", ""),
        project="ai-sdlc-lab/demo-app",
        repo_full_name="ai-sdlc-lab/demo-app",
        flow="code_review",
        agent="reviewer",
        risk_class="read_only_with_repo_context",
        status="completed",
        terminal_status="completed",
        summary="## Agent Review",
        artifact_root="/tmp",
        command_kind="review",
        issue_id=2,
        review_result=review,
        context_sources=["graph_blast_radius"],
        prompt_hash=None,
        prompt_hash_source="not_available",
        summary_hash="sum57abc",
        engine="fake_rlm",
        model_policy="fake",
        risk_tags=["prompt_injection"],
        commit_sha="abc123",
    )


def test_session_finished_admits_memory_with_evidence(tmp_path: Path, monkeypatch) -> None:
    state = tmp_path / "agent-state"
    state.mkdir()
    monkeypatch.setenv("AGENT_STATE_ROOT", str(state))

    s = begin_typed_session(
        state,
        project="ai-sdlc-lab/demo-app",
        command_kind="review",
        run_id="run-wb57",
        head_sha="abc123",
        trigger_context=_tc(),
    )
    event = _review_event(s.session_id)
    handle_ingest_session_update(state, event)

    loaded = load_session(state, "ai-sdlc-lab/demo-app", s.session_id)
    assert loaded is not None
    assert loaded.status == SessionStatus.FINISHED

    settings = Settings()
    db = MemoryStore(settings.memory_db_path)
    record = db.get_by_run_id("run-wb57")
    assert record is not None
    assert record.session_id == s.session_id
    assert record.epistemic_status == "inferred"
    assert record.memory_quality == "structured_result"
    assert record.admission_policy_version == ADMISSION_POLICY_VERSION_57
    assert any(r.startswith("verification:") for r in record.evidence_refs)
    assert f"session:{s.session_id}" in record.evidence_refs
    assert "verification_status:missing" in record.evidence_refs

    types = [e["type"] for e in load_project_events(state, "ai-sdlc-lab/demo-app")]
    assert "agent.verification_missing" in types
    assert "agent.session_finished" in types
    assert "agent.memory_admitted" in types
    assert types.index("agent.session_finished") < types.index("agent.memory_admitted")


def test_typed_ingest_defers_early_writeback(tmp_path: Path, monkeypatch) -> None:
    """Ingest must not write memory before session_finished for typed review."""
    state = tmp_path / "agent-state"
    state.mkdir()
    monkeypatch.setenv("AGENT_STATE_ROOT", str(state))

    s = begin_typed_session(
        state,
        project="ai-sdlc-lab/demo-app",
        command_kind="review",
        run_id="run-defer57",
        head_sha="abc123",
        trigger_context=_tc(),
    )
    inbox = tmp_path / "inbox.json"
    inbox.write_text(
        json.dumps(_review_event(s.session_id, run_id="run-defer57").model_dump(mode="json")),
        encoding="utf-8",
    )
    ingest_result_file(state, inbox)

    settings = Settings()
    db = MemoryStore(settings.memory_db_path)
    record = db.get_by_run_id("run-defer57")
    assert record is not None
    assert record.session_id == s.session_id
    assert record.epistemic_status == "inferred"

    types = [e["type"] for e in load_project_events(state, "ai-sdlc-lab/demo-app")]
    assert "agent.memory_admitted" in types


def test_failed_session_skips_admission(tmp_path: Path, monkeypatch) -> None:
    state = tmp_path / "agent-state"
    state.mkdir()
    monkeypatch.setenv("AGENT_STATE_ROOT", str(state))

    s = begin_typed_session(
        state,
        project="ai-sdlc-lab/demo-app",
        command_kind="review",
        run_id="run-fail57",
        head_sha="abc123",
        trigger_context=_tc(),
    )
    event = _review_event(s.session_id, run_id="run-fail57").model_copy(
        update={"status": "failed", "terminal_status": "failed", "review_result": None}
    )
    handle_ingest_session_update(state, event)

    settings = Settings()
    db = MemoryStore(settings.memory_db_path)
    assert db.get_by_run_id("run-fail57") is None
    types = [e["type"] for e in load_project_events(state, "ai-sdlc-lab/demo-app")]
    assert "agent.memory_admitted" not in types
    assert "agent.session_finished" not in types