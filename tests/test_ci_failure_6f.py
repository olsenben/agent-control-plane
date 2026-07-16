"""Tests for Slice 6F.1 failure evidence + hostile log handling."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agent_control.ci.failure_evidence import (
    ensure_failure_evidence,
    evidence_observation_id,
    load_manifest,
)
from agent_control.ci.gitea_actions_errors import GiteaActionsApiError, JobLogsResult, WorkflowJob
from agent_control.ci.log_sanitize import sanitize_ci_log
from agent_control.ci.observe import apply_observation
from agent_control.ci.pending import save_pending_ci
from agent_control.config import Settings
from agent_shared.models.ci import PendingCiRecord, RequiredWorkflow, WorkflowObservation


def test_evidence_observation_id_stable() -> None:
    a = evidence_observation_id(
        owner="o",
        repo="r",
        fix_run_id="run-1",
        pr_number=20,
        expected_head_sha="abc",
        workflow_run_id="449",
        workflow_run_attempt=1,
    )
    b = evidence_observation_id(
        owner="o",
        repo="r",
        fix_run_id="run-1",
        pr_number=20,
        expected_head_sha="abc",
        workflow_run_id="449",
        workflow_run_attempt=1,
    )
    assert a == b
    assert len(a) == 32


def test_sanitize_redacts_before_hash_and_strips_ansi() -> None:
    raw = (
        b"\x1b[31mERROR\x1b[0m token=ghp_ABCDEFG1234567890\n"
        b"traceback here\nAssertionError: boom\n"
    )
    sanitized = sanitize_ci_log(raw)
    assert "ghp_" not in sanitized.text
    assert "\x1b" not in sanitized.text
    assert sanitized.redaction_count >= 1
    assert sanitized.retained_sha256
    assert "raw" not in sanitized.truncation_strategy  # retained naming elsewhere


def test_ensure_failure_evidence_idempotent(tmp_path: Path) -> None:
    client = MagicMock()
    client.list_workflow_run_jobs.return_value = [
        WorkflowJob(job_id="12", name="test", status="completed", conclusion="failure"),
    ]
    client.download_job_logs.return_value = JobLogsResult(
        job_id="12",
        body=b"pytest failed\nAssertionError: x\n",
    )
    obs = WorkflowObservation(
        workflow_run_id="449",
        run_attempt=1,
        status="completed",
        conclusion="failure",
        head_sha="deadbeef",
        pr_number=20,
        path=".gitea/workflows/ci.yaml",
    )
    m1 = ensure_failure_evidence(
        tmp_path,
        fix_run_id="run-1",
        repository="ai-sdlc-lab/demo-app",
        expected_head_sha="deadbeef",
        observation=obs,
        gitea_client=client,
        settings=Settings(
            FIX_CI_OBSERVE_ENABLED=True,
            FIX_CI_FAILURE_EVIDENCE_ENABLED=True,
        ),
    )
    assert m1.status == "collected"
    assert client.download_job_logs.call_count == 1
    m2 = ensure_failure_evidence(
        tmp_path,
        fix_run_id="run-1",
        repository="ai-sdlc-lab/demo-app",
        expected_head_sha="deadbeef",
        observation=obs,
        gitea_client=client,
        settings=Settings(
            FIX_CI_OBSERVE_ENABLED=True,
            FIX_CI_FAILURE_EVIDENCE_ENABLED=True,
        ),
    )
    assert m2.evidence_observation_id == m1.evidence_observation_id
    assert client.download_job_logs.call_count == 1  # no re-download


def test_empty_jobs_contract_mismatch(tmp_path: Path) -> None:
    client = MagicMock()
    client.list_workflow_run_jobs.side_effect = GiteaActionsApiError(
        "empty_jobs",
        "empty",
        status_code=200,
    )
    obs = WorkflowObservation(
        workflow_run_id="450",
        run_attempt=1,
        status="completed",
        conclusion="failure",
        head_sha="deadbeef",
        pr_number=20,
    )
    manifest = ensure_failure_evidence(
        tmp_path,
        fix_run_id="run-1",
        repository="ai-sdlc-lab/demo-app",
        expected_head_sha="deadbeef",
        observation=obs,
        gitea_client=client,
        settings=Settings(FIX_CI_FAILURE_EVIDENCE_ENABLED=True),
    )
    assert manifest.status == "contract_mismatch"


def test_apply_observation_collects_evidence_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = tmp_path / "state"
    art = tmp_path / "artifacts" / "run-1"
    art.mkdir(parents=True)
    pending = PendingCiRecord(
        fix_run_id="run-1",
        repository="ai-sdlc-lab/demo-app",
        expected_head_commit_sha="deadbeefcafe",
        opened_pr_number=20,
        issue_id=19,
        agent_branch="agent/fix-1",
        required_workflows=[
            RequiredWorkflow(path=".gitea/workflows/ci.yaml", source="repo_default"),
        ],
        artifact_root=str(art),
    )
    save_pending_ci(state, pending)

    client = MagicMock()
    client.list_workflow_run_jobs.return_value = [
        WorkflowJob(job_id="7", name="ci", status="completed", conclusion="failure"),
    ]
    client.download_job_logs.return_value = JobLogsResult(
        job_id="7",
        body=b"FAILED tests/test_x.py::test_y\nAssertionError\n",
    )

    monkeypatch.setattr(
        "agent_control.ci.failure_evidence.GiteaClient",
        lambda settings=None: client,
    )
    monkeypatch.setattr(
        "agent_control.ci.evidence_comments.post_issue_comment",
        lambda *a, **k: {"ok": True},
    )
    monkeypatch.setattr(
        "agent_control.ci.comments.post_issue_comment",
        lambda *a, **k: {"ok": True},
    )

    settings = Settings(
        FIX_CI_OBSERVE_ENABLED=True,
        FIX_CI_FAILURE_EVIDENCE_ENABLED=True,
        FIX_CI_REPAIR_ENABLED=False,
        GITEA_BOT_TOKEN="t",
    )
    obs = WorkflowObservation(
        workflow_run_id="449",
        run_attempt=1,
        status="completed",
        conclusion="failure",
        head_sha="deadbeefcafe",
        pr_number=20,
        path=".gitea/workflows/ci.yaml",
        delivery_id="d1",
    )
    r1 = apply_observation(
        state,
        repository="ai-sdlc-lab/demo-app",
        head_sha="deadbeefcafe",
        observation=obs,
        settings=settings,
        post_comment=True,
    )
    assert r1 is not None
    assert r1.verdict == "failing"
    # replay same observation
    r2 = apply_observation(
        state,
        repository="ai-sdlc-lab/demo-app",
        head_sha="deadbeefcafe",
        observation=obs,
        settings=settings,
        post_comment=True,
    )
    assert r2 is not None
    assert client.download_job_logs.call_count == 1
    obs_id = evidence_observation_id(
        owner="ai-sdlc-lab",
        repo="demo-app",
        fix_run_id="run-1",
        pr_number=20,
        expected_head_sha="deadbeefcafe",
        workflow_run_id="449",
        workflow_run_attempt=1,
    )
    manifest = load_manifest(art, obs_id)
    assert manifest is not None
    assert manifest.status == "collected"


def test_repair_flag_requires_observe_and_evidence() -> None:
    with pytest.raises(ValueError, match="FIX_CI_REPAIR_ENABLED"):
        Settings(
            FIX_CI_REPAIR_ENABLED=True,
            FIX_CI_OBSERVE_ENABLED=False,
            FIX_CI_FAILURE_EVIDENCE_ENABLED=True,
        )
