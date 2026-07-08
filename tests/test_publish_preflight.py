"""Publish preflight tests (Slice 6D.1)."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from agent_shared.models.jobs import JobSafety, RLMJob
from agent_workers.gates.runner import APPROVED_PATCH_NAME
from agent_workers.publish.preflight import PublishPreflightError, run_publish_preflight
from agent_workers.settings import WorkerSettings


def _worker_settings(tmp_path: Path, *, publish: bool = True) -> WorkerSettings:
    return WorkerSettings(
        redis_url="redis://localhost:6379/0",
        agent_runs_dir=tmp_path / "runs",
        agent_cache_dir=tmp_path / "cache",
        agent_state_root=tmp_path / "state",
        gitea_base_url="http://gitea.local",
        gitea_agent_token="",
        gitea_bot_token="token",
        gitea_agent_comment_enabled=False,
        git_ro_key_path=None,
        model_policy="fake",
        fix_remote_publish_enabled=publish,
    )


def _init_git_repo(path: Path, *, with_identity: bool = True) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "README.md").write_text("hi\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    if with_identity:
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)


def _job(allow_push: bool = True) -> RLMJob:
    return RLMJob.model_validate(
        {
            "run_id": "run-pre",
            "job_id": "j-pre",
            "workflow_id": "run-pre",
            "session_id": "run-pre",
            "workflow_definition": "developer/v1",
            "flow_config_id": "developer",
            "flow_version": "0.1.0",
            "flow_config_schema_version": "v1",
            "project": "ai-sdlc-lab/demo",
            "owner": "ai-sdlc-lab",
            "repo": "demo",
            "repo_url": "http://example/repo",
            "primary_branch": "main",
            "policy_ref": "main",
            "base_ref": "main",
            "task_ref": "main",
            "proposed_agent_branch": "agent/run-pre",
            "trigger_event_id": "t-pre",
            "trigger_type": "gitea.issue_comment",
            "trigger_context": {
                "source": "gitea",
                "event_type": "gitea.issue_comment",
                "issue_number": 1,
            },
            "flow": "developer",
            "agent": "developer",
            "risk_class": "write_patch",
            "command_intent": {
                "activated": True,
                "activation": "/agent",
                "kind": "fix",
                "natural_language_task": "WI-1",
                "confidence": 1.0,
            },
            "safety": JobSafety(allow_repo_write=True, allow_push=allow_push).model_dump(mode="json"),
            "model_policy": "fake",
            "state_path": "/tmp/state.json",
            "fix_authorization": {
                "approval_id": "a",
                "approval_target_id": "WI-1",
                "plan_run_id": "run-plan",
                "plan_hash": "x",
                "blast_radius_hash": "y",
                "allowed_files": ["README.md"],
                "plan_summary": "s",
                "plan_steps": [],
                "ci_hints": [],
            },
        }
    )


def test_no_git_identity_raises_publish_preflight(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    artifact = tmp_path / "artifacts"
    artifact.mkdir()
    _init_git_repo(repo, with_identity=False)
    (artifact / APPROVED_PATCH_NAME).write_text(
        "diff --git a/README.md b/README.md\n--- a/README.md\n+++ b/README.md\n@@ -1 +1,2 @@\n hi\n+line\n",
        encoding="utf-8",
    )
    (repo / "README.md").write_text("hi\nline\n", encoding="utf-8")
    settings = _worker_settings(tmp_path)
    with patch("agent_workers.publish.preflight._git_identity_configured", return_value=False):
        with pytest.raises(PublishPreflightError) as exc:
            run_publish_preflight(
                repo_workspace=repo,
                artifact_root=artifact,
                job=_job(),
                settings=settings,
                allowed_files=["README.md"],
            )
    assert "identity" in str(exc.value).lower()


def test_publish_preflight_already_applied_workspace_uses_git_diff_not_git_apply(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    artifact = tmp_path / "artifacts"
    artifact.mkdir()
    _init_git_repo(repo)
    (artifact / APPROVED_PATCH_NAME).write_text(
        "diff --git a/README.md b/README.md\n--- a/README.md\n+++ b/README.md\n@@ -1 +1,2 @@\n hi\n+line\n",
        encoding="utf-8",
    )
    (repo / "README.md").write_text("hi\nline\n", encoding="utf-8")
    settings = _worker_settings(tmp_path)
    real_run = subprocess.run

    with patch("agent_workers.publish.preflight.subprocess.run") as mock_run:

        def _side_effect(cmd, **kwargs):
            if "apply" in cmd:
                raise AssertionError("git apply must not be used in workspace-mode preflight")
            return real_run(cmd, **kwargs)

        mock_run.side_effect = _side_effect
        run_publish_preflight(
            repo_workspace=repo,
            artifact_root=artifact,
            job=_job(),
            settings=settings,
            allowed_files=["README.md"],
        )


def test_git_worker_gitconfig_is_installed_or_loaded() -> None:
    root = Path(__file__).resolve().parents[1]
    gitconfig = root / "config" / "git-worker.gitconfig"
    assert gitconfig.is_file()
    text = gitconfig.read_text(encoding="utf-8")
    assert "[user]" in text
    assert "name = Agent Control Plane" in text
    assert "email = agent-control-plane@local" in text
    result = subprocess.run(
        ["git", "config", "--file", str(gitconfig), "user.name"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "Agent Control Plane"
    compose = (root / "docker-compose.ct104.yml").read_text(encoding="utf-8")
    assert "git-worker.gitconfig:/root/.gitconfig" in compose
