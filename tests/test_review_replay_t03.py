"""V5 T03 — review replay console from durable artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_control.config import Settings
from agent_control.memory.preflight_artifacts import (
    persist_context_packet_artifact,
    persist_preflight_artifact,
)
from agent_control.replay.review import ReviewReplayError, STAGE_ORDER, build_review_replay
from agent_control.session import begin_typed_session, handle_ingest_session_update, load_session
from agent_shared.models.agent_session import SessionStatus
from agent_shared.models.events import AgentRunCompletedEvent
from agent_shared.models.jobs import TriggerContext
from agent_shared.models.memory_preflight import ContextPacket, MemoryPreflight
from agent_shared.models.review import ReviewFinding, ReviewResult


def _tc() -> TriggerContext:
    return TriggerContext(
        event_type="gitea.issue_comment",
        issue_number=2,
        author="alice",
        raw_body="/agent review",
        normalized_body="/agent review",
    )


def _review_event(session_id: str, run_id: str = "run-replay-t03") -> AgentRunCompletedEvent:
    review = ReviewResult(
        findings=[ReviewFinding(id="F-T03", summary="replay finding")],
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
        summary_hash="sum-t03",
        engine="fake_rlm",
        model_policy="fake",
        risk_tags=["prompt_injection"],
        policy_decision="allow",
        commit_sha="abc123",
    )


def _attach_preflight(state: Path, session_id: str, run_id: str) -> None:
    preflight = MemoryPreflight(
        session_id=session_id,
        run_id=run_id,
        repo="ai-sdlc-lab/demo-app",
        issue_id=2,
        source_sha="abc123",
        policy_source_sha="poldeadbeef",
        created_at="2026-07-20T00:00:00+00:00",
        status="complete",
    )
    stamped, _, _ = persist_preflight_artifact(state, preflight)
    packet = ContextPacket(
        session_id=session_id,
        run_id=run_id,
        repo="ai-sdlc-lab/demo-app",
        source_sha="abc123",
        policy_source_sha="poldeadbeef",
        preflight_digest=stamped.artifact_digest,
        preflight_relative_path=f"sessions/{session_id}/memory_preflight.json",
        context_pack_digest="packdigest",
        created_at="2026-07-20T00:00:01+00:00",
    )
    persist_context_packet_artifact(state, packet)


def test_review_replay_end_to_end_stages(tmp_path: Path, monkeypatch) -> None:
    state = tmp_path / "agent-state"
    state.mkdir()
    monkeypatch.setenv("AGENT_STATE_ROOT", str(state))

    session = begin_typed_session(
        state,
        project="ai-sdlc-lab/demo-app",
        command_kind="review",
        run_id="run-replay-t03",
        head_sha="abc123",
        policy_source_sha="poldeadbeef",
        trigger_context=_tc(),
    )
    _attach_preflight(state, session.session_id, "run-replay-t03")
    inbox = tmp_path / "inbox.json"
    inbox.write_text(
        json.dumps(_review_event(session.session_id).model_dump(mode="json")),
        encoding="utf-8",
    )
    from agent_control.results_ingest import ingest_result_file

    ingest_result_file(state, inbox)

    loaded = load_session(state, "ai-sdlc-lab/demo-app", session.session_id)
    assert loaded is not None
    assert loaded.status == SessionStatus.FINISHED

    settings = Settings()
    doc = build_review_replay(
        state,
        project="ai-sdlc-lab/demo-app",
        session_id=session.session_id,
        memory_db_path=settings.memory_db_path,
    )

    assert doc["schema_version"] == "review_replay.v1"
    assert doc["complete"] is True
    assert doc["stage_order"] == list(STAGE_ORDER)
    assert all(doc["stages_present"][s] for s in STAGE_ORDER)

    issue = doc["stages"]["issue"]
    assert issue["subject_kind"] == "issue"
    assert issue["subject_number"] == 2
    assert issue["invoked_by"] == "alice"

    context = doc["stages"]["context"]
    assert context["memory_preflight"]["status"] == "complete"
    assert context["memory_preflight"]["policy_source_sha"] == "poldeadbeef"
    assert context["context_packet"]["context_pack_digest"] == "packdigest"

    model = doc["stages"]["model"]
    assert model["model_policy"] == "fake"
    assert model["engine"] == "fake_rlm"

    policy = doc["stages"]["policy"]
    assert policy["policy_source_sha"] == "poldeadbeef"
    assert policy["policy_decision"] == "allow"

    memory = doc["stages"]["memory"]
    assert memory["record"] is not None
    assert memory["record"]["session_id"] == session.session_id
    assert memory["record"]["epistemic_status"] == "inferred"
    assert memory["record"]["findings_count"] == 1

    types = [row["type"] for row in doc["timeline"]]
    assert "agent.session_started" in types
    assert "agent.run_completed" in types
    assert "agent.session_finished" in types
    assert "agent.memory_admitted" in types


def test_review_replay_by_run_id(tmp_path: Path, monkeypatch) -> None:
    state = tmp_path / "agent-state"
    state.mkdir()
    monkeypatch.setenv("AGENT_STATE_ROOT", str(state))

    session = begin_typed_session(
        state,
        project="ai-sdlc-lab/demo-app",
        command_kind="review",
        run_id="run-replay-by-run",
        head_sha="abc123",
        trigger_context=_tc(),
    )
    _attach_preflight(state, session.session_id, "run-replay-by-run")
    handle_ingest_session_update(
        state, _review_event(session.session_id, run_id="run-replay-by-run")
    )

    settings = Settings()
    doc = build_review_replay(
        state,
        project="ai-sdlc-lab/demo-app",
        run_id="run-replay-by-run",
        memory_db_path=settings.memory_db_path,
    )
    assert doc["session_id"] == session.session_id
    assert doc["complete"] is True


def test_review_replay_rejects_unfinished(tmp_path: Path, monkeypatch) -> None:
    state = tmp_path / "agent-state"
    state.mkdir()
    monkeypatch.setenv("AGENT_STATE_ROOT", str(state))

    session = begin_typed_session(
        state,
        project="ai-sdlc-lab/demo-app",
        command_kind="review",
        run_id="run-replay-open",
        head_sha="abc123",
        trigger_context=_tc(),
    )
    with pytest.raises(ReviewReplayError, match="finished"):
        build_review_replay(
            state,
            project="ai-sdlc-lab/demo-app",
            session_id=session.session_id,
            require_finished=True,
        )

    doc = build_review_replay(
        state,
        project="ai-sdlc-lab/demo-app",
        session_id=session.session_id,
        require_finished=False,
    )
    assert doc["status"] != SessionStatus.FINISHED.value
    assert doc["stages_present"]["issue"] is True
