"""Dry-run publish status and artifact contract."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from agent_shared.constants import (
    FIX_STATUS_LOCAL_PATCH_PASSED,
    FIX_STATUS_PR_OPENED_PENDING_CI,
    TERMINAL_STATUS_COMPLETED,
)
from agent_workers.publish.remote import fix_status_for_publish_result, publish_fix_branch_and_pr
from test_publish_6d import _fix_job, _fix_result, _init_git_repo, _worker_settings


def test_dry_run_status_contract(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    head = _init_git_repo(repo)
    (repo / "README.md").write_text("# Changed\n", encoding="utf-8")
    artifact = tmp_path / "art"
    artifact.mkdir()
    job = _fix_job(tmp_path, head=head, run_id="run-dry-contract")
    mock_client = MagicMock()
    with patch("agent_workers.publish.remote.run_closed_world_diff_gate") as mock_gate:
        mock_gate.return_value = MagicMock(passed=True, model_dump=lambda mode="json": {"passed": True})
        result = publish_fix_branch_and_pr(
            repo_workspace=repo,
            policy_workspace=repo,
            artifact_root=artifact,
            job=job,
            fix_result=_fix_result(),
            settings=_worker_settings(tmp_path),
            dry_run=True,
            gitea_client=mock_client,
        )
    assert result.publish_state == "dry_run_passed"
    assert result.dry_run is True
    assert fix_status_for_publish_result(result) == FIX_STATUS_LOCAL_PATCH_PASSED
    assert fix_status_for_publish_result(result) != FIX_STATUS_PR_OPENED_PENDING_CI
    mock_client.get_branch_sha.assert_not_called()
    mock_client.create_pull_request.assert_not_called()
    assert (artifact / "remote_publish_plan.json").is_file()
    assert not (artifact / "remote_publish_result.json").exists()
    # Documented completed terminal path for dry-run (no real publish lifecycle)
    assert TERMINAL_STATUS_COMPLETED == "completed"
