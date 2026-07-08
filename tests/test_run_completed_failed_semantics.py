"""Failed run_completed semantics tests."""

import json
from pathlib import Path
from unittest.mock import patch

from agent_control.memory.mapper import memory_record_from_completed
from agent_control.results_ingest import ingest_result_file
from agent_shared.models.events import AgentRunCompletedEvent
from agent_shared.models.plan import PlanResult, PlanStep


def test_failed_run_skips_memory_writeback(tmp_path: Path) -> None:
    event = AgentRunCompletedEvent(
        run_id="run-fail-mem",
        job_id="j1",
        workflow_id="run-fail-mem",
        session_id="run-fail-mem",
        trigger_event_id="t1",
        project="ai-sdlc-lab/demo",
        flow="planner",
        agent="planner",
        risk_class="planning_only",
        status="failed",
        terminal_status="failed_parse",
        summary="parse failed",
        artifact_root="/tmp",
        command_kind="plan",
        plan_result=PlanResult(steps=[PlanStep(id="S1", summary="s", files=["a.py"])]),
    )
    assert memory_record_from_completed(event) is None


def test_ingest_preserves_terminal_status(tmp_path: Path) -> None:
    state = tmp_path / "state"
    inbox_dir = state / "inbox" / "ct104-results"
    inbox_dir.mkdir(parents=True)
    inbox = inbox_dir / "run-term.json"
    payload = {
        "schema_version": "agent_run_completed.v1",
        "run_id": "run-term",
        "job_id": "j1",
        "workflow_id": "run-term",
        "session_id": "run-term",
        "trigger_event_id": "t1",
        "project": "ai-sdlc-lab/demo",
        "flow": "planner",
        "agent": "planner",
        "risk_class": "planning_only",
        "status": "failed",
        "terminal_status": "failed_parse",
        "summary": "failed",
        "artifact_root": "/tmp",
        "command_kind": "plan",
    }
    inbox.write_text(json.dumps(payload), encoding="utf-8")

    with patch("agent_control.results_ingest.writeback_from_completed") as mock_wb:
        stored, created = ingest_result_file(state, inbox)
        mock_wb.assert_not_called()
    assert created is True
    stored_data = json.loads(stored.read_text(encoding="utf-8"))
    assert stored_data["payload"]["terminal_status"] == "failed_parse"


def test_ingest_preserves_failed_quality_gate_terminal_status(tmp_path: Path) -> None:
    state = tmp_path / "state"
    inbox_dir = state / "inbox" / "ct104-results"
    inbox_dir.mkdir(parents=True)
    inbox = inbox_dir / "run-qg.json"
    payload = {
        "schema_version": "agent_run_completed.v1",
        "run_id": "run-qg",
        "job_id": "j1",
        "workflow_id": "run-qg",
        "session_id": "run-qg",
        "trigger_event_id": "t1",
        "project": "ai-sdlc-lab/demo",
        "flow": "planner",
        "agent": "planner",
        "risk_class": "planning_only",
        "status": "failed",
        "terminal_status": "failed_quality_gate",
        "summary": "hollow plan",
        "artifact_root": "/tmp",
        "command_kind": "plan",
    }
    inbox.write_text(json.dumps(payload), encoding="utf-8")

    with patch("agent_control.results_ingest.writeback_from_completed") as mock_wb:
        stored, created = ingest_result_file(state, inbox)
        mock_wb.assert_not_called()
    assert created is True
    stored_data = json.loads(stored.read_text(encoding="utf-8"))
    assert stored_data["payload"]["terminal_status"] == "failed_quality_gate"
