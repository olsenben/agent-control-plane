"""Tests for CT104 result ingest."""

import json
from pathlib import Path

from agent_control.results_ingest import ingest_result_file
from agent_shared.models.events import AgentRunCompletedEvent


def test_ingest_result_file(tmp_path: Path) -> None:
    event = AgentRunCompletedEvent(
        run_id="run-abc",
        job_id="rlm-root-abc",
        workflow_id="run-abc",
        session_id="run-abc",
        trigger_event_id="abc",
        project="ai-sdlc-lab/demo-app",
        flow="inspect",
        agent="explainer",
        risk_class="read_only",
        status="completed",
        summary="ok",
        artifact_root="/mnt/agent-runs/demo",
    )
    inbox_file = tmp_path / "inbox.json"
    inbox_file.write_text(json.dumps(event.model_dump(mode="json")), encoding="utf-8")
    stored, created = ingest_result_file(tmp_path, inbox_file)
    assert created is True
    assert stored.exists()
