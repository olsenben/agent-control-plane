"""Tests for run_completed_builder inbox enrichment."""

import json
from pathlib import Path

from agent_shared.models.review import ReviewResult
from agent_workers.jobs.run_completed_builder import build_run_completed_event


def test_build_run_completed_includes_review_result(tmp_path: Path) -> None:
    artifact_root = tmp_path / "run1"
    artifact_root.mkdir()
    review = ReviewResult(files_inspected=["README.md"])
    job = {
        "job_id": "rlm-root-r1",
        "workflow_id": "run-r1",
        "session_id": "run-r1",
        "trigger_event_id": "r1",
        "flow": "code_review",
        "agent": "reviewer",
        "risk_class": "read_only_with_repo_context",
        "model_policy": "fake",
        "task_ref": "main",
        "target_sha": "abc123",
        "command_intent": {"kind": "review"},
        "trigger_context": {"issue_number": 7},
        "context_pack": {"context_sources": ["graph_blast_radius"]},
    }
    result = {
        "flow": "code_review",
        "agent": "reviewer",
        "risk_class": "read_only_with_repo_context",
        "status": "completed",
        "engine": "fake_rlm",
        "review_result": review.model_dump(mode="json"),
        "summary": "## Agent Review",
    }
    (artifact_root / "context_receipt.json").write_text(
        json.dumps({"sources": ["graph_blast_radius", "gitea_issue"]}),
        encoding="utf-8",
    )

    event = build_run_completed_event(
        run_id="run-r1",
        project="ai-sdlc-lab/demo-app",
        artifact_root=artifact_root,
        job=job,
        result=result,
        summary="## Agent Review",
    )
    assert event.command_kind == "review"
    assert event.issue_id == 7
    assert event.repo_full_name == "ai-sdlc-lab/demo-app"
    assert event.review_result is not None
    assert event.prompt_hash is None
    assert event.prompt_hash_source == "not_available"
    assert event.summary_hash is not None
    assert "graph_blast_radius" in event.context_sources


def test_build_run_completed_inspect_omits_structured_results(tmp_path: Path) -> None:
    artifact_root = tmp_path / "run2"
    artifact_root.mkdir()
    job = {
        "command_intent": {"kind": "inspect"},
        "trigger_context": {},
    }
    result = {"flow": "inspect", "status": "completed", "summary": "ok"}
    event = build_run_completed_event(
        run_id="run-i1",
        project="ai-sdlc-lab/demo-app",
        artifact_root=artifact_root,
        job=job,
        result=result,
        summary="ok",
    )
    assert event.command_kind == "inspect"
    assert event.review_result is None
    assert event.plan_result is None
