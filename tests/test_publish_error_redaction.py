"""Publish errors must not leak credentials into artifacts."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent_shared.models.approval import FixAuthorizationBinding
from agent_shared.models.fix import FixResult
from agent_shared.models.jobs import RLMJob
from agent_workers.publish.remote import PublishError, publish_fix_branch_and_pr
from agent_workers.settings import WorkerSettings


def _init_git_repo(path: Path) -> str:
    path.mkdir(parents=True, exist_ok=True)
    (path / "README.md").write_text("# Demo\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)
    proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=path, capture_output=True, text=True, check=True)
    return proc.stdout.strip()


def test_publish_error_redaction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "super-bot-token-xyz"
    monkeypatch.setenv("GITEA_BOT_TOKEN", secret)
    repo = tmp_path / "repo"
    head = _init_git_repo(repo)
    (repo / "README.md").write_text("# Changed\n", encoding="utf-8")
    artifact = tmp_path / "art"
    artifact.mkdir()
    binding = FixAuthorizationBinding(
        approval_id="appr-1",
        approval_target_id="WI-0004-abcd1234",
        plan_run_id="run-plan-1",
        plan_hash="planhash",
        blast_radius_hash="brhash",
        allowed_files=["README.md"],
        approved_base_sha=head,
        approved_base_ref="main",
    )
    job = RLMJob.model_validate(
        {
            "run_id": "run-redact",
            "job_id": "j1",
            "workflow_id": "run-redact",
            "session_id": "run-redact",
            "workflow_definition": "developer/v1",
            "flow_config_id": "developer",
            "flow_version": "0.1.0",
            "flow_config_schema_version": "v1",
            "project": "ai-sdlc-lab/demo",
            "owner": "ai-sdlc-lab",
            "repo": "demo",
            "repo_url": "http://gitea.local/ai-sdlc-lab/demo.git",
            "primary_branch": "main",
            "policy_ref": "main",
            "base_ref": "main",
            "target_sha": None,
            "task_ref": "main",
            "proposed_agent_branch": "agent/run-redact",
            "trigger_event_id": "t1",
            "trigger_delivery_id": None,
            "trigger_type": "manual",
            "trigger_context": {"event_type": "manual"},
            "flow": "developer",
            "agent": "developer",
            "risk_class": "write_patch",
            "command_intent": {"kind": "fix"},
            "reporting": {},
            "limits": {},
            "safety": {"allow_push": True},
            "model_policy": "fake",
            "state_path": str(tmp_path / "v.json"),
            "fix_authorization": binding.model_dump(mode="json"),
        }
    )
    fix = FixResult.model_validate(
        {
            "schema_version": "fix_result.v1",
            "scope_summary": "test",
            "files_changed": ["README.md"],
            "changes": [{"path": "README.md", "edit_kind": "replace", "content": "# Changed\n"}],
            "confidence": "high",
        }
    )
    settings = WorkerSettings(
        redis_url="redis://localhost:6379/0",
        agent_runs_dir=tmp_path / "runs",
        agent_cache_dir=tmp_path / "cache",
        agent_state_root=tmp_path / "state",
        gitea_base_url="http://gitea.local",
        gitea_agent_token="",
        gitea_bot_token=secret,
        gitea_agent_comment_enabled=False,
        git_ro_key_path=None,
        model_policy="fake",
        fix_remote_publish_enabled=True,
    )
    mock_client = MagicMock()
    mock_client.get_branch_sha.side_effect = lambda _o, _r, branch: head if branch == "main" else None

    import agent_workers.publish.remote as remote_mod

    real_git_run = remote_mod._git_run

    def fake_git_run(repo_root: Path, cmd: list[str], *, env: dict[str, str] | None = None):
        if len(cmd) >= 2 and cmd[0] == "git" and cmd[1] == "push":
            err = (
                f"fatal: unable to access 'http://oauth2:{secret}@gitea.local/demo.git/': "
                f"Authorization: Bearer {secret}"
            )
            return subprocess.CompletedProcess(cmd, 1, "", err)
        return real_git_run(repo_root, cmd, env=env)

    with patch("agent_workers.publish.remote.run_closed_world_diff_gate") as mock_gate:
        mock_gate.return_value = MagicMock(passed=True, model_dump=lambda mode="json": {"passed": True})
        with patch("agent_workers.publish.remote._git_run", side_effect=fake_git_run):
            with patch(
                "agent_workers.publish.remote.resolve_authenticated_repo_url",
                return_value=f"http://oauth2:{secret}@gitea.local/ai-sdlc-lab/demo.git",
            ):
                with pytest.raises(PublishError) as exc:
                    publish_fix_branch_and_pr(
                        repo_workspace=repo,
                        policy_workspace=repo,
                        artifact_root=artifact,
                        job=job,
                        fix_result=fix,
                        settings=settings,
                        gitea_client=mock_client,
                    )
    assert secret not in str(exc.value)
    assert "oauth2:" not in str(exc.value) or "[REDACTED]" in str(exc.value)
