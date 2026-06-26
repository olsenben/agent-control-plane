"""Ingest watch sweep tests."""

import json
from pathlib import Path

from agent_control.results_ingest import ingest_inbox


def test_ingest_sweep_processes_pending_file(tmp_path: Path) -> None:
    state = tmp_path / "state"
    inbox = state / "inbox" / "ct104-results"
    inbox.mkdir(parents=True)
    path = inbox / "run-sweep.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "agent_run_completed.v1",
                "run_id": "run-sweep",
                "job_id": "j1",
                "workflow_id": "run-sweep",
                "session_id": "run-sweep",
                "trigger_event_id": "t1",
                "project": "ai-sdlc-lab/demo",
                "flow": "inspect",
                "agent": "explainer",
                "risk_class": "read_only",
                "status": "completed",
                "terminal_status": "completed",
                "summary": "ok",
                "artifact_root": "/tmp",
            }
        ),
        encoding="utf-8",
    )
    results = ingest_inbox(state)
    assert len(results) == 1
    assert results[0]["created"] is True
    assert path.with_suffix(".json.processed").is_file()
