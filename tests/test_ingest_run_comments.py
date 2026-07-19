"""CT103 posts Risk 0/1 run summaries on results ingest (V4.1.1)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from agent_control.results_ingest import ingest_result_file
from agent_shared.models.events import AgentRunCompletedEvent


def _write_inbox(tmp_path: Path, event: AgentRunCompletedEvent) -> Path:
    inbox = tmp_path / "inbox.json"
    inbox.write_text(json.dumps(event.model_dump(mode="json")), encoding="utf-8")
    return inbox


def test_ingest_posts_plan_summary_comment(tmp_path: Path) -> None:
    event = AgentRunCompletedEvent(
        run_id="run-plan-comment",
        job_id="j1",
        workflow_id="run-plan-comment",
        session_id="run-plan-comment",
        trigger_event_id="t1",
        project="ai-sdlc-lab/demo-app",
        issue_id=7,
        flow="planner",
        agent="planner",
        risk_class="planning_only",
        status="completed",
        command_kind="plan",
        summary="## Agent Plan\n\n### Scope\nok",
        artifact_root="/tmp",
    )
    with patch("agent_control.results_ingest.post_issue_comment") as mock_post:
        mock_post.return_value = {"id": 1}
        ingest_result_file(tmp_path, _write_inbox(tmp_path, event))
    mock_post.assert_called_once()
    assert mock_post.call_args[0][0] == "ai-sdlc-lab/demo-app"
    assert mock_post.call_args[0][1] == 7
    assert "Agent Plan" in mock_post.call_args[0][2]


def test_ingest_posts_failed_fix_summary(tmp_path: Path) -> None:
    event = AgentRunCompletedEvent(
        run_id="run-fix-fail-comment",
        job_id="j2",
        workflow_id="run-fix-fail-comment",
        session_id="run-fix-fail-comment",
        trigger_event_id="t2",
        project="ai-sdlc-lab/demo-app",
        issue_id=7,
        flow="developer",
        agent="developer",
        risk_class="write_patch",
        status="failed",
        command_kind="fix",
        summary="## Fix failed\n\nGate denied",
        artifact_root="/tmp",
    )
    with patch("agent_control.results_ingest.post_issue_comment") as mock_post:
        mock_post.return_value = {"id": 2}
        ingest_result_file(tmp_path, _write_inbox(tmp_path, event))
    mock_post.assert_called_once()


def test_ingest_skips_comment_for_successful_fix_without_issue(tmp_path: Path) -> None:
    event = AgentRunCompletedEvent(
        run_id="run-fix-ok",
        job_id="j3",
        workflow_id="run-fix-ok",
        session_id="run-fix-ok",
        trigger_event_id="t3",
        project="ai-sdlc-lab/demo-app",
        issue_id=None,
        flow="developer",
        agent="developer",
        risk_class="write_patch",
        status="completed",
        command_kind="fix",
        summary="should not post",
        artifact_root="/tmp",
    )
    with patch("agent_control.results_ingest.post_issue_comment") as mock_post:
        ingest_result_file(tmp_path, _write_inbox(tmp_path, event))
    mock_post.assert_not_called()
