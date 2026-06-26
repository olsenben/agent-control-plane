"""Redis-enqueued ingest tests (Slice 4C)."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from agent_control.results_ingest import inbox_content_hash, ingest_result_file
from agent_workers.jobs.report import process_report


def test_ingest_enqueue_from_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = tmp_path / "state"
    runs = tmp_path / "runs" / "ai-sdlc-lab" / "demo" / "run-ingest-1"
    runs.mkdir(parents=True)
    state.mkdir()
    monkeypatch.setenv("AGENT_STATE_ROOT", str(state))
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    (runs / "metadata.json").write_text('{"status":"running"}', encoding="utf-8")
    (runs / "result.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "terminal_status": "completed",
                "flow": "planner",
                "agent": "planner",
                "risk_class": "planning_only",
            }
        ),
        encoding="utf-8",
    )

    with patch("agent_workers.jobs.report.enqueue_ingest_inbox_file") as mock_enqueue:
        mock_enqueue.return_value = "ingest-job-1"
        report = process_report(
            {
                "run_id": "run-ingest-1",
                "project": "ai-sdlc-lab/demo",
                "artifact_root": str(runs),
                "job": {
                    "flow": "planner",
                    "command_intent": {"kind": "plan"},
                    "trigger_context": {"issue_number": 1},
                },
                "result": {
                    "status": "completed",
                    "terminal_status": "completed",
                    "flow": "planner",
                    "agent": "planner",
                    "risk_class": "planning_only",
                    "summary": "done",
                },
            }
        )
    inbox = Path(report["inbox_path"])
    content_hash = inbox_content_hash(inbox)
    mock_enqueue.assert_called_once()
    args = mock_enqueue.call_args.args
    assert args[1] == "run-ingest-1"
    assert args[3] == content_hash


def test_ingest_job_content_hash_idempotent(tmp_path: Path) -> None:
    state = tmp_path / "state"
    inbox_dir = state / "inbox" / "ct104-results"
    inbox_dir.mkdir(parents=True)
    inbox = inbox_dir / "run-hash.json"
    payload = {
        "schema_version": "agent_run_completed.v1",
        "run_id": "run-hash",
        "job_id": "j1",
        "workflow_id": "run-hash",
        "session_id": "run-hash",
        "trigger_event_id": "t1",
        "project": "ai-sdlc-lab/demo",
        "flow": "planner",
        "agent": "planner",
        "risk_class": "planning_only",
        "status": "completed",
        "terminal_status": "completed",
        "summary": "ok",
        "artifact_root": "/tmp",
        "command_kind": "plan",
    }
    inbox.write_text(json.dumps(payload), encoding="utf-8")
    stored1, created1 = ingest_result_file(state, inbox)
    assert created1 is True
    payload_text = json.dumps(payload)
    inbox.write_text(payload_text, encoding="utf-8")
    stored2, created2 = ingest_result_file(state, inbox)
    assert created2 is False
    assert stored1 == stored2
