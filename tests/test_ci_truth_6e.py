"""Slice 6E.1 / 6E.2 CI truth loop tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from agent_control.ci.aggregate import (
    evaluate_aggregate,
    merge_observation,
    normalize_conclusion,
    result_from_pending,
    workflow_paths_match,
)
from agent_control.ci.artifacts import load_verification_current, write_observation_artifact
from agent_control.ci.memory import memory_record_from_ci_verified, writeback_fix_ci_verified
from agent_control.ci.observe import apply_observation, extract_workflow_run_fields, handle_workflow_event
from agent_control.ci.pending import (
    find_pending_by_repo_sha,
    list_pending_ci,
    register_pending_ci,
)
from agent_control.config import Settings
from agent_control.events import AgentEvent, append_event, deterministic_event_id
from agent_shared.models.ci import (
    CiVerificationResult,
    RequiredWorkflow,
    WorkflowObservation,
)
from agent_shared.models.events import AgentRunCompletedEvent
from agent_shared.models.fix import FixFileChange, FixResult


def _settings(tmp_path: Path, **kwargs: Any) -> Settings:
    data: dict[str, Any] = {
        "agent_state_root": tmp_path,
        "fix_ci_observe_enabled": True,
        "fix_ci_require_matrix_match": True,
        "fix_ci_repo_default_workflow": ".gitea/workflows/ci.yaml",
        "gitea_bot_token": "",
    }
    data.update(kwargs)
    return Settings.model_construct(**data)


def _req(path: str) -> RequiredWorkflow:
    return RequiredWorkflow(path=path, display_name=path, source="matrix")


def _obs(
    *,
    path: str,
    conclusion: str,
    sha: str,
    run_id: str = "100",
    attempt: int = 1,
    delivery: str | None = "d1",
) -> WorkflowObservation:
    return WorkflowObservation(
        path=path,
        display_name=path,
        workflow_run_id=run_id,
        run_attempt=attempt,
        status="completed",
        conclusion=normalize_conclusion(conclusion),
        head_sha=sha,
        delivery_id=delivery,
        observed_at="2026-07-13T00:00:00Z",
        api_verification_status="confirmed",
    )


def test_exact_pr_wrong_sha_does_not_correlate(tmp_path: Path) -> None:
    register_pending_ci(
        tmp_path,
        fix_run_id="run-1",
        repository="ai-sdlc-lab/agent-control-plane",
        expected_head_commit_sha="aaa111",
        opened_pr_number=20,
        required_workflows=[_req(".gitea/workflows/ci.yaml")],
    )
    found = find_pending_by_repo_sha(
        tmp_path, "ai-sdlc-lab/agent-control-plane", "bbb222"
    )
    assert found is None


def test_same_sha_other_repo_does_not_correlate(tmp_path: Path) -> None:
    register_pending_ci(
        tmp_path,
        fix_run_id="run-1",
        repository="ai-sdlc-lab/agent-control-plane",
        expected_head_commit_sha="aaa111",
        required_workflows=[_req(".gitea/workflows/ci.yaml")],
    )
    found = find_pending_by_repo_sha(tmp_path, "other-org/other-repo", "aaa111")
    assert found is None


def test_two_workflows_first_success_still_pending() -> None:
    result = CiVerificationResult(
        fix_run_id="run-1",
        repository="ai-sdlc-lab/agent-control-plane",
        expected_head_commit_sha="sha1",
        required_workflows=[
            _req(".gitea/workflows/ci.yaml"),
            _req(".gitea/workflows/lint.yaml"),
        ],
    )
    result = merge_observation(
        result,
        _obs(path=".gitea/workflows/ci.yaml", conclusion="success", sha="sha1", run_id="1"),
    )
    assert result.verdict == "pending"
    assert ".gitea/workflows/lint.yaml" in result.missing_workflows


def test_one_fails_after_success_is_failing() -> None:
    result = CiVerificationResult(
        fix_run_id="run-1",
        repository="ai-sdlc-lab/agent-control-plane",
        expected_head_commit_sha="sha1",
        required_workflows=[
            _req(".gitea/workflows/ci.yaml"),
            _req(".gitea/workflows/lint.yaml"),
        ],
    )
    result = merge_observation(
        result,
        _obs(path=".gitea/workflows/ci.yaml", conclusion="success", sha="sha1", run_id="1"),
    )
    result = merge_observation(
        result,
        _obs(path=".gitea/workflows/lint.yaml", conclusion="failure", sha="sha1", run_id="2"),
    )
    assert result.verdict == "failing"


def test_failed_then_successful_rerun_verified() -> None:
    result = CiVerificationResult(
        fix_run_id="run-1",
        repository="ai-sdlc-lab/agent-control-plane",
        expected_head_commit_sha="sha1",
        required_workflows=[_req(".gitea/workflows/ci.yaml")],
    )
    result = merge_observation(
        result,
        _obs(
            path=".gitea/workflows/ci.yaml",
            conclusion="failure",
            sha="sha1",
            run_id="10",
            attempt=1,
        ),
    )
    assert result.verdict == "failing"
    result = merge_observation(
        result,
        _obs(
            path=".gitea/workflows/ci.yaml",
            conclusion="success",
            sha="sha1",
            run_id="10",
            attempt=2,
        ),
    )
    assert result.verdict == "verified"


def test_gitea_path_ref_suffix_matches_repo_default() -> None:
    """Gitea Actions returns ``ci.yaml@refs/...``; required uses ``.gitea/workflows/ci.yaml``."""
    assert workflow_paths_match(
        ".gitea/workflows/ci.yaml",
        "ci.yaml@refs/pull/20/head",
    )
    assert workflow_paths_match(
        ".gitea/workflows/ci.yaml",
        "ci.yaml@refs/heads/agent/run-cf4c2b2edaf8643b833456660b0a2f85",
    )
    assert not workflow_paths_match(
        ".gitea/workflows/ci.yaml",
        "lint.yaml@refs/pull/20/head",
    )
    result = CiVerificationResult(
        fix_run_id="run-1",
        repository="ai-sdlc-lab/agent-control-plane",
        expected_head_commit_sha="ef22",
        required_workflows=[_req(".gitea/workflows/ci.yaml")],
        observations=[
            _obs(
                path="ci.yaml@refs/heads/agent/run-x",
                conclusion="success",
                sha="ef22",
                run_id="450",
            ),
            _obs(
                path="ci.yaml@refs/pull/20/head",
                conclusion="success",
                sha="ef22",
                run_id="449",
            ),
        ],
    )
    result = evaluate_aggregate(result)
    assert result.verdict == "verified"
    assert result.missing_workflows == []


def test_duplicate_observation_idempotent(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    artifact = tmp_path / "artifacts" / "run-1"
    artifact.mkdir(parents=True)
    register_pending_ci(
        tmp_path,
        fix_run_id="run-1",
        repository="ai-sdlc-lab/agent-control-plane",
        expected_head_commit_sha="sha1",
        issue_id=19,
        required_workflows=[_req(".gitea/workflows/ci.yaml")],
        artifact_root=str(artifact),
    )
    obs = _obs(path=".gitea/workflows/ci.yaml", conclusion="success", sha="sha1", delivery="dup")
    r1 = apply_observation(
        tmp_path,
        repository="ai-sdlc-lab/agent-control-plane",
        head_sha="sha1",
        observation=obs,
        settings=settings,
        post_comment=False,
    )
    r2 = apply_observation(
        tmp_path,
        repository="ai-sdlc-lab/agent-control-plane",
        head_sha="sha1",
        observation=obs,
        settings=settings,
        post_comment=False,
    )
    assert r1 is not None and r2 is not None
    assert r1.verdict == "verified"
    assert len(r2.observations) == 1


def test_unknown_conclusion_fail_closed() -> None:
    assert normalize_conclusion(None) == "unknown"
    assert normalize_conclusion("weird") == "unknown"
    result = CiVerificationResult(
        fix_run_id="run-1",
        repository="ai-sdlc-lab/agent-control-plane",
        expected_head_commit_sha="sha1",
        required_workflows=[_req(".gitea/workflows/ci.yaml")],
    )
    result = merge_observation(
        result,
        _obs(path=".gitea/workflows/ci.yaml", conclusion="weird", sha="sha1"),
    )
    assert result.verdict == "failing"


def test_empty_matrix_does_not_accept_arbitrary_ci() -> None:
    result = CiVerificationResult(
        fix_run_id="run-1",
        repository="ai-sdlc-lab/agent-control-plane",
        expected_head_commit_sha="sha1",
        required_workflows=[],
    )
    result = merge_observation(
        result,
        _obs(path=".gitea/workflows/docker-ci.yaml", conclusion="success", sha="sha1"),
    )
    assert result.verdict == "pending"
    assert "empty_required_matrix" in result.reason_codes


def test_new_sha_supersedes_old_pending(tmp_path: Path) -> None:
    register_pending_ci(
        tmp_path,
        fix_run_id="run-old",
        repository="ai-sdlc-lab/agent-control-plane",
        expected_head_commit_sha="sha-old",
        opened_pr_number=20,
        required_workflows=[_req(".gitea/workflows/ci.yaml")],
    )
    register_pending_ci(
        tmp_path,
        fix_run_id="run-new",
        repository="ai-sdlc-lab/agent-control-plane",
        expected_head_commit_sha="sha-new",
        opened_pr_number=20,
        required_workflows=[_req(".gitea/workflows/ci.yaml")],
    )
    items = list_pending_ci(tmp_path, "ai-sdlc-lab/agent-control-plane", include_terminal=True)
    by_id = {i.fix_run_id: i for i in items}
    assert by_id["run-old"].current_verdict == "superseded"
    assert by_id["run-new"].current_verdict == "pending"


def test_api_contradicts_webhook_api_wins(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    register_pending_ci(
        tmp_path,
        fix_run_id="run-1",
        repository="ai-sdlc-lab/agent-control-plane",
        expected_head_commit_sha="api-sha",
        required_workflows=[_req(".gitea/workflows/ci.yaml")],
        artifact_root=str(tmp_path / "art"),
    )
    (tmp_path / "art").mkdir(parents=True)

    client = MagicMock()
    client.get_workflow_run.return_value = {
        "id": 55,
        "run_attempt": 1,
        "status": "completed",
        "conclusion": "success",
        "head_sha": "api-sha",
        "path": ".gitea/workflows/ci.yaml",
        "name": "ci",
        "workflow_id": "1",
    }

    event = {
        "type": "gitea.workflow_passed",
        "delivery_id": "del-1",
        "project": "ai-sdlc-lab/agent-control-plane",
        "payload": {
            "repository": {"full_name": "ai-sdlc-lab/agent-control-plane"},
            "workflow_run": {
                "id": 55,
                "run_attempt": 1,
                "status": "completed",
                "conclusion": "failure",  # webhook lies
                "head_sha": "api-sha",
                "path": ".gitea/workflows/ci.yaml",
                "name": "ci",
            },
        },
    }
    out = handle_workflow_event(
        tmp_path, event, settings=settings, gitea_client=client
    )
    assert out["handled"] is True
    assert out["verdict"] == "verified"
    assert out["api_verification_status"] == "contradicted"


def test_display_name_collision_path_distinguishes() -> None:
    result = CiVerificationResult(
        fix_run_id="run-1",
        repository="ai-sdlc-lab/agent-control-plane",
        expected_head_commit_sha="sha1",
        required_workflows=[
            _req(".gitea/workflows/ci.yaml"),
            _req(".gitea/workflows/ci-nightly.yaml"),
        ],
    )
    result = merge_observation(
        result,
        WorkflowObservation(
            path=".gitea/workflows/ci.yaml",
            display_name="CI",
            workflow_run_id="1",
            run_attempt=1,
            status="completed",
            conclusion="success",
            head_sha="sha1",
            api_verification_status="confirmed",
        ),
    )
    assert result.verdict == "pending"
    result = merge_observation(
        result,
        WorkflowObservation(
            path=".gitea/workflows/ci-nightly.yaml",
            display_name="CI",
            workflow_run_id="2",
            run_attempt=1,
            status="completed",
            conclusion="success",
            head_sha="sha1",
            api_verification_status="confirmed",
        ),
    )
    assert result.verdict == "verified"


def test_comment_failure_does_not_rollback_ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path)
    artifact = tmp_path / "artifacts" / "run-1"
    artifact.mkdir(parents=True)
    register_pending_ci(
        tmp_path,
        fix_run_id="run-1",
        repository="ai-sdlc-lab/agent-control-plane",
        expected_head_commit_sha="sha1",
        issue_id=19,
        required_workflows=[_req(".gitea/workflows/ci.yaml")],
        artifact_root=str(artifact),
    )

    def boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("gitea down")

    monkeypatch.setattr("agent_control.ci.comments.post_issue_comment", boom)

    result = apply_observation(
        tmp_path,
        repository="ai-sdlc-lab/agent-control-plane",
        head_sha="sha1",
        observation=_obs(path=".gitea/workflows/ci.yaml", conclusion="success", sha="sha1"),
        settings=settings,
        post_comment=True,
    )
    assert result is not None
    assert result.verdict == "verified"
    # Ledger events still present
    from agent_control.events import load_project_events

    types = [e["type"] for e in load_project_events(tmp_path, "ai-sdlc-lab/agent-control-plane")]
    assert "agent.fix_ci_observed" in types
    assert "agent.fix_ci_verdict_changed" in types


def test_memory_writeback_idempotent_on_verified(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings.memory_db_path.parent.mkdir(parents=True, exist_ok=True)
    # Point memory under tmp
    object.__setattr__(settings, "agent_state_root", tmp_path)

    sha = "abcdef0123456789"
    pending = register_pending_ci(
        tmp_path,
        fix_run_id="run-fix-1",
        repository="ai-sdlc-lab/agent-control-plane",
        expected_head_commit_sha=sha,
        issue_id=19,
        opened_pr_number=20,
        required_workflows=[_req(".gitea/workflows/ci.yaml")],
    )
    completed = AgentRunCompletedEvent(
        run_id="run-fix-1",
        job_id="job-1",
        workflow_id="wf-1",
        session_id="s1",
        trigger_event_id="t1",
        project="ai-sdlc-lab/agent-control-plane",
        flow="developer",
        agent="fixer",
        risk_class="write_patch",
        status="completed",
        summary="fix",
        artifact_root=str(tmp_path / "art"),
        command_kind="fix",
        repo_full_name="ai-sdlc-lab/agent-control-plane",
        issue_id=19,
        opened_pr_number=20,
        head_commit_sha=sha,
        agent_branch="agent/run-fix-1",
        fix_status="pr_opened_pending_ci",
        fix_result=FixResult(
            changes=[FixFileChange(path="README.md", content="x")],
        ),
    )
    event_id = deterministic_event_id("ct104", "run-fix-1", "agent.run_completed")
    append_event(
        tmp_path,
        AgentEvent(
            event_id=event_id,
            type="agent.run_completed",
            source="ct104",
            delivery_id="run-fix-1",
            project="ai-sdlc-lab/agent-control-plane",
            payload=completed.model_dump(mode="json"),
        ),
    )
    result = result_from_pending(pending)
    result = merge_observation(
        result,
        _obs(path=".gitea/workflows/ci.yaml", conclusion="success", sha=sha),
    )
    assert result.verdict == "verified"

    r1 = writeback_fix_ci_verified(
        tmp_path, pending=pending, result=result, settings=settings
    )
    r2 = writeback_fix_ci_verified(
        tmp_path, pending=pending, result=result, settings=settings
    )
    assert r1 is not None
    assert r1.memory_quality == "ci_verified"
    assert r2 is not None
    assert r1.record_id == r2.record_id


def test_extract_workflow_run_fields() -> None:
    fields = extract_workflow_run_fields(
        {
            "repository": {"full_name": "o/r"},
            "workflow_run": {
                "id": 9,
                "run_attempt": 2,
                "status": "completed",
                "conclusion": "success",
                "head_sha": "deadbeef",
                "path": ".gitea/workflows/ci.yaml",
                "name": "CI",
                "pull_requests": [{"number": 20}],
            },
        }
    )
    assert fields["workflow_run_id"] == "9"
    assert fields["run_attempt"] == 2
    assert fields["head_sha"] == "deadbeef"
    assert fields["pr_number"] == 20


def test_observation_artifact_immutable(tmp_path: Path) -> None:
    obs = _obs(path=".gitea/workflows/ci.yaml", conclusion="success", sha="sha1")
    p1 = write_observation_artifact(tmp_path, obs)
    obs2 = obs.model_copy(update={"conclusion": "failure"})
    p2 = write_observation_artifact(tmp_path, obs2)
    assert p1 == p2
    data = load_verification_current(tmp_path)
    assert data is None  # only observation written
    assert "success" in p1.read_text(encoding="utf-8")


def test_cancelled_is_failing() -> None:
    result = CiVerificationResult(
        fix_run_id="run-1",
        repository="ai-sdlc-lab/agent-control-plane",
        expected_head_commit_sha="sha1",
        required_workflows=[_req(".gitea/workflows/ci.yaml")],
    )
    result = merge_observation(
        result,
        _obs(path=".gitea/workflows/ci.yaml", conclusion="cancelled", sha="sha1"),
    )
    assert result.verdict == "failing"


def test_ingest_does_not_register_pending_from_legacy_pr_opened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """V4.1.1: worker-reported pr_opened_pending_ci must not register pending CI."""
    from agent_control.results_ingest import handle_fix_ingest_side_effects

    monkeypatch.setenv("FIX_CI_REQUIRE_MATRIX_MATCH", "true")
    settings = _settings(tmp_path)
    monkeypatch.setattr("agent_control.config.get_settings", lambda: settings)
    monkeypatch.setattr("agent_control.results_ingest.get_settings", lambda: settings)

    event = AgentRunCompletedEvent(
        run_id="run-ingest-1",
        job_id="j",
        workflow_id="w",
        session_id="s",
        trigger_event_id="t",
        project="ai-sdlc-lab/agent-control-plane",
        flow="developer",
        agent="fixer",
        risk_class="write_patch",
        status="completed",
        summary="fix",
        artifact_root=str(tmp_path / "art"),
        command_kind="fix",
        repo_full_name="ai-sdlc-lab/agent-control-plane",
        issue_id=19,
        opened_pr_number=20,
        head_commit_sha="deadbeefdeadbeef",
        agent_branch="agent/run-ingest-1",
        fix_status="pr_opened_pending_ci",
        fix_result=FixResult(ci_hints=[".gitea/workflows/ci.yaml"]),
    )
    handle_fix_ingest_side_effects(tmp_path, event)
    pending = find_pending_by_repo_sha(
        tmp_path, "ai-sdlc-lab/agent-control-plane", "deadbeefdeadbeef"
    )
    assert pending is None

    # Authoritative registration remains register_pending_ci (broker / observe)
    register_pending_ci(
        tmp_path,
        fix_run_id="run-ingest-1",
        repository="ai-sdlc-lab/agent-control-plane",
        expected_head_commit_sha="deadbeefdeadbeef",
        opened_pr_number=20,
        issue_id=19,
        agent_branch="agent/run-ingest-1",
        required_workflows=[_req(".gitea/workflows/ci.yaml")],
    )
    pending = find_pending_by_repo_sha(
        tmp_path, "ai-sdlc-lab/agent-control-plane", "deadbeefdeadbeef"
    )
    assert pending is not None
    assert pending.fix_run_id == "run-ingest-1"
    assert pending.required_workflows
    assert pending.required_workflows[0].path == ".gitea/workflows/ci.yaml"


def test_pending_survives_sha_index_corruption(tmp_path: Path) -> None:
    register_pending_ci(
        tmp_path,
        fix_run_id="run-1",
        repository="ai-sdlc-lab/agent-control-plane",
        expected_head_commit_sha="sha1",
        required_workflows=[_req(".gitea/workflows/ci.yaml")],
    )
    from agent_control.ci.pending import sha_index_path

    idx = sha_index_path(tmp_path, "ai-sdlc-lab/agent-control-plane", "sha1")
    idx.write_text("{not-json", encoding="utf-8")
    found = find_pending_by_repo_sha(tmp_path, "ai-sdlc-lab/agent-control-plane", "sha1")
    assert found is not None
    assert found.fix_run_id == "run-1"

    event = AgentRunCompletedEvent(
        run_id="run-x",
        job_id="j",
        workflow_id="w",
        session_id="s",
        trigger_event_id="t",
        project="ai-sdlc-lab/agent-control-plane",
        flow="developer",
        agent="fixer",
        risk_class="write_patch",
        status="completed",
        summary="fix",
        artifact_root="/tmp",
        command_kind="fix",
        repo_full_name="ai-sdlc-lab/agent-control-plane",
        issue_id=1,
        head_commit_sha="abc",
    )
    record = memory_record_from_ci_verified(event, head_commit_sha="abc123sha")
    assert record is not None
    assert record.memory_quality == "ci_verified"
    assert record.source_command == "fix"
    assert "abc123sha"[:12] in record.record_id
