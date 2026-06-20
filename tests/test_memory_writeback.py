"""Tests for memory writeback on result ingest."""

import json
from pathlib import Path

from agent_control.memory.store import MemoryStore
from agent_control.results_ingest import ingest_result_file
from agent_shared.models.events import AgentRunCompletedEvent
from agent_shared.models.review import ReviewFinding, ReviewResult


def _review_inbox_event(run_id: str = "run-mem1") -> dict:
    review = ReviewResult(
        findings=[ReviewFinding(id="F-001", summary="test finding")],
        files_inspected=["README.md"],
        risk_tags=["prompt_injection"],
    )
    event = AgentRunCompletedEvent(
        run_id=run_id,
        job_id=f"rlm-root-{run_id}",
        workflow_id=run_id,
        session_id=run_id,
        trigger_event_id=run_id.replace("run-", ""),
        project="ai-sdlc-lab/demo-app",
        repo_full_name="ai-sdlc-lab/demo-app",
        flow="code_review",
        agent="reviewer",
        risk_class="read_only_with_repo_context",
        status="completed",
        summary="## Agent Review",
        artifact_root="/mnt/agent-runs/demo",
        command_kind="review",
        issue_id=2,
        review_result=review,
        context_sources=["graph_blast_radius"],
        prompt_hash=None,
        prompt_hash_source="not_available",
        summary_hash="abc123",
        engine="fake_rlm",
        model_policy="fake",
        risk_tags=["prompt_injection"],
    )
    return event.model_dump(mode="json")


def test_ingest_writes_memory_row(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_STATE_ROOT", str(tmp_path))
    inbox = tmp_path / "inbox.json"
    inbox.write_text(json.dumps(_review_inbox_event()), encoding="utf-8")

    stored, created = ingest_result_file(tmp_path, inbox)
    assert created is True
    assert stored.exists()

    db = MemoryStore(tmp_path / "memory" / "memory.sqlite")
    record = db.get_by_run_id("run-mem1")
    assert record is not None
    assert record.issue_id == 2
    assert record.findings[0].summary == "test finding"
    assert record.audit.prompt_hash is None
    assert record.audit.prompt_hash_source == "not_available"
    assert "prompt_injection" in record.governance.risk_tags

    event_payload = json.loads(stored.read_text(encoding="utf-8"))["payload"]
    assert "prompt_injection" in event_payload["risk_tags"]
    assert event_payload["policy_decision"] == "allow"


def test_ingest_idempotent_memory_upsert(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_STATE_ROOT", str(tmp_path))
    inbox = tmp_path / "inbox.json"
    inbox.write_text(json.dumps(_review_inbox_event()), encoding="utf-8")

    ingest_result_file(tmp_path, inbox)
    db = MemoryStore(tmp_path / "memory" / "memory.sqlite")
    assert db.summary()["memory_records"] == 1

    inbox2 = tmp_path / "inbox2.json"
    inbox2.write_text(json.dumps(_review_inbox_event()), encoding="utf-8")
    _, created2 = ingest_result_file(tmp_path, inbox2)
    assert created2 is False
    assert db.summary()["memory_records"] == 1
