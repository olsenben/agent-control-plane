"""Publish state machine + ingest enqueue CAS (V4.1.1)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from agent_control.publish.state import (
    load_publish_record,
    try_enqueue_cas,
)
from agent_control.results_ingest import handle_fix_ingest_side_effects
from agent_shared.constants import (
    FIX_STATUS_PATCH_BUNDLE_READY,
    PRODUCER_PROTOCOL_PATCH_BUNDLE_V1,
)
from agent_shared.models.events import AgentRunCompletedEvent


def test_cas_enqueue_once(tmp_path: Path) -> None:
    r1 = try_enqueue_cas(
        tmp_path,
        run_id="run-1",
        kind="fix",
        attempt_id="1",
        bundle_id="b1",
        project="ai-sdlc-lab/demo-app",
    )
    assert r1 is not None
    assert r1.publish_state == "queued"
    r2 = try_enqueue_cas(
        tmp_path,
        run_id="run-1",
        kind="fix",
        attempt_id="1",
        bundle_id="b1",
        project="ai-sdlc-lab/demo-app",
    )
    assert r2 is None
    loaded = load_publish_record(tmp_path, "run-1", "b1")
    assert loaded is not None
    assert loaded.publish_state == "queued"


def test_ingest_enqueues_patch_bundle_ready(tmp_path: Path) -> None:
    event = AgentRunCompletedEvent(
        run_id="run-enq",
        job_id="j1",
        workflow_id="w1",
        session_id="s1",
        trigger_event_id="t1",
        project="ai-sdlc-lab/demo-app",
        flow="developer_flow",
        agent="developer",
        risk_class="write_patch",
        status="completed",
        terminal_status="completed",
        summary="ok",
        artifact_root=str(tmp_path),
        command_kind="fix",
        issue_id=1,
        approval_id="appr",
        approval_target_id="tgt",
        fix_status=FIX_STATUS_PATCH_BUNDLE_READY,
        producer_protocol=PRODUCER_PROTOCOL_PATCH_BUNDLE_V1,
        bundle_id="bundlexyz",
        attempt_id="1",
        bundle_kind="fix",
    )
    settings = MagicMock()
    settings.fix_remote_publish_enabled = True
    settings.redis_url = "redis://localhost:6379/0"
    settings.gitea_bot_token = ""

    with patch("agent_control.queue.enqueue_publish", return_value="job-1") as enq:
        with patch("agent_control.gitea_comments.post_issue_comment", return_value=None):
            handle_fix_ingest_side_effects(tmp_path, event, settings=settings)
    enq.assert_called_once()
    rec = load_publish_record(tmp_path, "run-enq", "bundlexyz")
    assert rec is not None
    assert rec.publish_state == "queued"


def test_ingest_ignores_legacy_pr_opened(tmp_path: Path) -> None:
    event = AgentRunCompletedEvent(
        run_id="run-legacy",
        job_id="j1",
        workflow_id="w1",
        session_id="s1",
        trigger_event_id="t1",
        project="ai-sdlc-lab/demo-app",
        flow="developer_flow",
        agent="developer",
        risk_class="write_patch",
        status="completed",
        summary="ok",
        artifact_root=str(tmp_path),
        command_kind="fix",
        issue_id=1,
        approval_id="appr",
        approval_target_id="tgt",
        fix_status="pr_opened_pending_ci",
        head_commit_sha="abc",
        # no producer_protocol
    )
    settings = MagicMock()
    settings.fix_remote_publish_enabled = True
    with patch("agent_control.queue.enqueue_publish") as enq:
        handle_fix_ingest_side_effects(tmp_path, event, settings=settings)
    enq.assert_not_called()
