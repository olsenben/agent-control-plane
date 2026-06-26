"""Plan inbox fallback tests (Slice 4C)."""

import json
from pathlib import Path
from unittest.mock import patch

from agent_control.approval.plan_lookup import resolve_plan_for_target
from agent_shared.approval_ids import derive_approval_target_id
from agent_shared.hash_utils import hash_plan_result
from agent_shared.models.plan import PlanResult, PlanStep


def _plan_payload(run_id: str, issue_id: int = 4) -> dict:
    plan = PlanResult(
        steps=[PlanStep(id="S1", summary="step", files=["README.md"])],
        approval_target_id=derive_approval_target_id(issue_id=issue_id, plan_run_id=run_id),
    )
    return {
        "schema_version": "agent_run_completed.v1",
        "run_id": run_id,
        "job_id": "j1",
        "workflow_id": run_id,
        "session_id": run_id,
        "trigger_event_id": "t1",
        "project": "ai-sdlc-lab/agent-control-plane",
        "flow": "planner",
        "agent": "planner",
        "risk_class": "planning_only",
        "status": "completed",
        "terminal_status": "completed",
        "summary": "plan ok",
        "artifact_root": "/tmp",
        "command_kind": "plan",
        "issue_id": issue_id,
        "plan_result": plan.model_dump(mode="json"),
        "plan_hash": hash_plan_result(plan),
        "approval_target_id": plan.approval_target_id,
    }


def test_plan_inbox_fallback_resolves_without_ledger(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox" / "ct104-results"
    inbox.mkdir(parents=True)
    run_id = "run-c29ad349c1f560bc6b989732d4c92e62"
    target = derive_approval_target_id(issue_id=6, plan_run_id=run_id)
    path = inbox / f"{run_id}.json"
    path.write_text(json.dumps(_plan_payload(run_id, issue_id=6)), encoding="utf-8")

    with patch("agent_control.approval.plan_lookup.enqueue_ingest_inbox_file") as mock_enqueue:
        mock_enqueue.return_value = "ingest-1"
        record = resolve_plan_for_target(
            tmp_path,
            "ai-sdlc-lab/agent-control-plane",
            6,
            target,
        )

    assert record.resolution_source == "inbox_fallback"
    assert record.inbox_path == str(path)
    mock_enqueue.assert_called_once()


def test_plan_fallback_triggers_ingest_repair(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox" / "ct104-results"
    inbox.mkdir(parents=True)
    run_id = "run-planaaaaabbbcccddd"
    path = inbox / f"{run_id}.json"
    path.write_text(json.dumps(_plan_payload(run_id)), encoding="utf-8")

    with patch("agent_control.approval.plan_lookup.enqueue_ingest_inbox_file") as mock_enqueue:
        mock_enqueue.return_value = "job-123"
        record = resolve_plan_for_target(
            tmp_path,
            "ai-sdlc-lab/agent-control-plane",
            4,
            derive_approval_target_id(issue_id=4, plan_run_id=run_id),
        )
    assert record.ingest_job_id == "job-123"
