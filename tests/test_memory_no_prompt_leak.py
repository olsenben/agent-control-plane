"""Ensure memory rows do not store prompts or secrets."""

import json
from pathlib import Path

from agent_control.memory.store import MemoryStore
from agent_control.results_ingest import ingest_result_file
from agent_shared.models.events import AgentRunCompletedEvent
from agent_shared.models.review import ReviewFinding, ReviewResult

FORBIDDEN_SUBSTRINGS = [
    "GITEA_AGENT_TOKEN",
    "Authorization: Bearer",
    "BEGIN PRIVATE KEY",
    "sk-live-",
    "You are performing a code review",
    "Respond with a single JSON object",
]


def test_memory_row_has_no_prompt_or_secrets(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_STATE_ROOT", str(tmp_path))
    fake_prompt = (
        "You are performing a code review. Respond with a single JSON object only.\n"
        "GITEA_AGENT_TOKEN=super-secret\nAuthorization: Bearer sk-live-abc\n"
        "-----BEGIN PRIVATE KEY-----\n"
    )
    review = ReviewResult(
        findings=[ReviewFinding(id="F-001", summary="surface issue only")],
        files_inspected=["README.md"],
    )
    event = AgentRunCompletedEvent(
        run_id="run-leak1",
        job_id="j",
        workflow_id="run-leak1",
        session_id="run-leak1",
        trigger_event_id="leak1",
        project="ai-sdlc-lab/demo-app",
        repo_full_name="ai-sdlc-lab/demo-app",
        flow="code_review",
        agent="reviewer",
        risk_class="read_only_with_repo_context",
        status="completed",
        summary=f"## Agent Review\n{fake_prompt[:200]}",
        artifact_root="/mnt/agent-runs/demo",
        command_kind="review",
        issue_id=3,
        review_result=review,
    )
    inbox = tmp_path / "inbox.json"
    inbox.write_text(json.dumps(event.model_dump(mode="json")), encoding="utf-8")
    ingest_result_file(tmp_path, inbox)

    db = MemoryStore(tmp_path / "memory" / "memory.sqlite")
    row = db.get_by_run_id("run-leak1")
    assert row is not None
    blob = json.dumps(row.model_dump(mode="json"))
    lowered = blob.lower()
    for needle in FORBIDDEN_SUBSTRINGS:
        assert needle.lower() not in lowered, f"forbidden substring found: {needle}"

    with db.connect() as conn:
        raw = conn.execute(
            "SELECT record_json FROM memory_records WHERE run_id = ?",
            ("run-leak1",),
        ).fetchone()
    assert raw is not None
    raw_text = raw["record_json"].lower()
    for needle in FORBIDDEN_SUBSTRINGS:
        assert needle.lower() not in raw_text, f"forbidden substring in sqlite: {needle}"
