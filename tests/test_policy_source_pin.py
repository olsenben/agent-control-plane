"""V4.1.1 PR1 — policy_source_* pin + fail-closed policy workspace."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent_control.project_registry import (
    PolicySourcePin,
    PolicySourcePinError,
    normalize_policy_remote,
    pin_from_job_fields,
    resolve_policy_source_pin,
)
from agent_workers.repo.policy_loader import (
    PolicyWorkspaceError,
    checkout_pinned_policy_workspace,
    verify_pinned_policy_workspace,
)
from agent_workers.settings import WorkerSettings


def _git(cwd: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout.strip()


def _init_repo(path: Path) -> str:
    path.mkdir(parents=True)
    _git(path, "init")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "test")
    (path / ".agent").mkdir()
    (path / ".agent" / "agent-config.yml").write_text("agents: {}\n", encoding="utf-8")
    (path / "README.md").write_text("ok\n", encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-m", "init")
    return _git(path, "rev-parse", "HEAD")


def test_normalize_policy_remote_strips_creds_and_git_suffix() -> None:
    assert (
        normalize_policy_remote("https://oauth2:secret@git.example/ai/demo.git")
        == "https://git.example/ai/demo"
    )


def test_pin_from_job_fields_none_without_sha() -> None:
    assert pin_from_job_fields(project="a/b", repo_url="http://g/a/b.git") is None


def test_resolve_policy_source_pin_reuses_existing() -> None:
    existing = PolicySourcePin(
        policy_source_repo="ai-sdlc-lab/demo-app",
        policy_source_remote="http://192.168.4.60:3000/ai-sdlc-lab/demo-app",
        policy_source_ref="main",
        policy_source_sha="abc1234567890",
    )
    with patch("agent_control.gitea_client.GiteaClient") as client_cls:
        got = resolve_policy_source_pin("ai-sdlc-lab/demo-app", existing=existing)
    client_cls.assert_not_called()
    assert got is existing


def test_resolve_policy_source_pin_fail_closed_on_empty_sha() -> None:
    settings = MagicMock()
    settings.gitea_base_url = "http://192.168.4.60:3000"
    with (
        patch("agent_control.project_registry.resolve_project") as resolve_project,
        patch("agent_control.gitea_client.GiteaClient") as client_cls,
    ):
        resolve_project.return_value = MagicMock(
            protected_policy_ref="main",
            default_branch="main",
            repo_url="http://192.168.4.60:3000/ai-sdlc-lab/demo-app.git",
        )
        client_cls.return_value.get_branch_sha.return_value = ""
        with pytest.raises(PolicySourcePinError, match="empty policy SHA"):
            resolve_policy_source_pin("ai-sdlc-lab/demo-app", settings=settings)


def test_verify_pinned_policy_workspace_head_mismatch(tmp_path: Path) -> None:
    sha = _init_repo(tmp_path / "repo")
    pin = PolicySourcePin(
        policy_source_repo="ai/demo",
        policy_source_remote="file:///tmp/unused",
        policy_source_ref="main",
        policy_source_sha="deadbeef" * 5,
    )
    # Plant matching remote marker/url so only HEAD fails
    _git(tmp_path / "repo", "remote", "add", "origin", pin.policy_source_remote)
    with pytest.raises(PolicyWorkspaceError, match="policy HEAD"):
        verify_pinned_policy_workspace(tmp_path / "repo", pin)
    assert sha  # repo created


def test_verify_pinned_policy_workspace_remote_mismatch(tmp_path: Path) -> None:
    sha = _init_repo(tmp_path / "repo")
    pin = PolicySourcePin(
        policy_source_repo="ai/demo",
        policy_source_remote="http://trusted.example/ai/demo",
        policy_source_ref="main",
        policy_source_sha=sha,
    )
    _git(tmp_path / "repo", "remote", "add", "origin", "http://attacker.example/ai/demo.git")
    with pytest.raises(PolicyWorkspaceError, match="remote identity mismatch"):
        verify_pinned_policy_workspace(tmp_path / "repo", pin)


def test_checkout_pinned_policy_workspace_detached(tmp_path: Path) -> None:
    origin = tmp_path / "origin.git"
    work = tmp_path / "seed"
    sha = _init_repo(work)
    # bare mirror for clone
    subprocess.run(["git", "clone", "--bare", str(work), str(origin)], check=True, capture_output=True)

    pin = PolicySourcePin(
        policy_source_repo="ai/demo",
        policy_source_remote=f"file://{origin}",
        policy_source_ref="main",
        policy_source_sha=sha,
    )
    # normalize_policy_remote on file:// may drop path oddly — use clone_url override matching pin remote
    # For file URLs, normalize keeps path; set pin remote to normalized form of origin
    pin = PolicySourcePin(
        policy_source_repo="ai/demo",
        policy_source_remote=normalize_policy_remote(f"file://{origin}"),
        policy_source_ref="main",
        policy_source_sha=sha,
    )
    settings = WorkerSettings(
        redis_url="redis://localhost",
        agent_runs_dir=tmp_path / "runs",
        agent_cache_dir=tmp_path / "cache",
        agent_state_root=tmp_path / "state",
        gitea_base_url="http://192.168.4.60:3000",
        gitea_agent_token="",
        gitea_bot_token="",
        gitea_agent_comment_enabled=False,
        git_ro_key_path=None,
        model_policy="fake",
        fix_remote_publish_enabled=False,
    )
    dest = tmp_path / "policy_repo"
    # monkeypatch auth to pass URL through
    with patch(
        "agent_workers.repo.policy_loader.authenticated_repo_url_from_credentials",
        side_effect=lambda url, creds_path=None: url,
    ):
        checkout_pinned_policy_workspace(
            settings,
            pin,
            dest,
            clone_url=f"file://{origin}",
        )
    head = _git(dest, "rev-parse", "HEAD")
    assert head == sha
    # detached
    branch = subprocess.run(
        ["git", "symbolic-ref", "-q", "HEAD"],
        cwd=dest,
        capture_output=True,
        text=True,
    )
    assert branch.returncode != 0


def test_runner_fails_closed_without_task_branch_fallback(tmp_path: Path) -> None:
    from agent_shared.models.intent import CommandIntent
    from agent_shared.models.jobs import RLMJob
    from agent_workers.flows import runner as runner_mod

    job = RLMJob(
        run_id="run-pin-fail",
        job_id="j1",
        workflow_id="run-pin-fail",
        session_id="run-pin-fail",
        workflow_definition="inspect",
        flow_config_id="inspect",
        flow_version="1",
        flow_config_schema_version="1",
        project="ai-sdlc-lab/demo-app",
        owner="ai-sdlc-lab",
        repo="demo-app",
        repo_url="http://192.168.4.60:3000/ai-sdlc-lab/demo-app.git",
        policy_source_repo="ai-sdlc-lab/demo-app",
        policy_source_remote="http://192.168.4.60:3000/ai-sdlc-lab/demo-app",
        policy_source_ref="main",
        policy_source_sha="abc1234",
        policy_schema_version="policy_source.v1",
        trigger_event_id="t1",
        trigger_type="gitea.issue_comment",
        trigger_context={"source": "gitea", "event_type": "gitea.issue_comment"},
        flow="inspect",
        agent="explainer",
        risk_class="read_only",
        command_intent=CommandIntent(
            activated=True,
            activation="/agent",
            kind="inspect",
            natural_language_task="x",
            confidence=1.0,
        ),
    )
    settings = WorkerSettings(
        redis_url="redis://localhost",
        agent_runs_dir=tmp_path / "runs",
        agent_cache_dir=tmp_path / "cache",
        agent_state_root=tmp_path / "state",
        gitea_base_url="http://192.168.4.60:3000",
        gitea_agent_token="",
        gitea_bot_token="",
        gitea_agent_comment_enabled=False,
        git_ro_key_path=None,
        model_policy="fake",
        fix_remote_publish_enabled=False,
    )

    def boom(*_a, **_k):
        raise PolicyWorkspaceError("simulated pin checkout failure")

    with patch.object(runner_mod, "checkout_pinned_policy_workspace", side_effect=boom):
        with patch.object(runner_mod, "clone_repo") as clone_mock:
            with patch.object(
                runner_mod,
                "finalize_failed_run",
                side_effect=lambda **kwargs: {
                    "status": "failed",
                    "run_id": job.run_id,
                    "error": str(kwargs.get("exc")),
                },
            ):
                result = runner_mod.run_flow_session(job.model_dump(mode="json"), settings=settings)
    clone_mock.assert_not_called()
    assert result["status"] == "failed"
    assert "simulated pin checkout failure" in (result.get("error") or "")
