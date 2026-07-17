"""Tests for repair fast-forward push helper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from agent_workers.publish import remote as remote_mod
from agent_workers.settings import WorkerSettings


def _settings() -> WorkerSettings:
    return WorkerSettings(
        redis_url="redis://localhost:6379/0",
        agent_runs_dir=Path("/tmp/runs"),
        agent_cache_dir=Path("/tmp/cache"),
        agent_state_root=Path("/tmp/state"),
        gitea_base_url="https://git.example.com",
        gitea_agent_token="",
        gitea_bot_token="tok",
        gitea_agent_comment_enabled=False,
        git_ro_key_path=None,
        model_policy="fake",
        fix_remote_publish_enabled=True,
    )


def test_push_repair_stale_when_remote_moved(tmp_path: Path, monkeypatch) -> None:
    ws = tmp_path / "repo"
    ws.mkdir()
    client = MagicMock()
    client.get_branch_sha.return_value = "other"

    out = remote_mod.push_repair_fast_forward(
        repo_workspace=ws,
        agent_branch="agent/run-1",
        expected_remote_sha="abc",
        repository="o/r",
        repo_url="https://git.example.com/o/r.git",
        settings=_settings(),
        gitea_client=client,
    )
    assert out["ok"] is False
    assert out["stale"] is True
    assert out["reason"] == "remote_head_changed"


def test_push_repair_never_force(tmp_path: Path, monkeypatch) -> None:
    ws = tmp_path / "repo"
    ws.mkdir()
    client = MagicMock()
    client.get_branch_sha.return_value = "abc"

    monkeypatch.setattr(remote_mod, "_git_head", lambda _p: "def")
    monkeypatch.setattr(
        remote_mod,
        "_git_run",
        lambda *a, **k: MagicMock(returncode=0, stdout="", stderr=""),
    )
    monkeypatch.setattr(remote_mod, "resolve_authenticated_repo_url", lambda u: u)
    monkeypatch.setattr(remote_mod, "_ensure_origin", lambda *a, **k: None)

    calls: list[list[str]] = []

    def capture(repo, cmd, env=None):
        calls.append(cmd)
        if cmd[:2] == ["git", "merge-base"]:
            return MagicMock(returncode=0, stdout="", stderr="")
        if cmd[0:2] == ["git", "push"]:
            return MagicMock(returncode=0, stdout="", stderr="")
        return MagicMock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(remote_mod, "_git_run", capture)

    out = remote_mod.push_repair_fast_forward(
        repo_workspace=ws,
        agent_branch="agent/run-1",
        expected_remote_sha="abc",
        repository="o/r",
        repo_url="https://git.example.com/o/r.git",
        settings=_settings(),
        gitea_client=client,
    )
    assert out["ok"] is True
    push_cmds = [c for c in calls if c[:2] == ["git", "push"]]
    assert push_cmds
    assert "--force" not in push_cmds[0]
    assert push_cmds[0] == ["git", "push", "origin", "HEAD:refs/heads/agent/run-1"]


def test_push_repair_rejected_is_stale(tmp_path: Path, monkeypatch) -> None:
    ws = tmp_path / "repo"
    ws.mkdir()
    client = MagicMock()
    client.get_branch_sha.return_value = "abc"
    monkeypatch.setattr(remote_mod, "_git_head", lambda _p: "def")
    monkeypatch.setattr(remote_mod, "resolve_authenticated_repo_url", lambda u: u)
    monkeypatch.setattr(remote_mod, "_ensure_origin", lambda *a, **k: None)

    def run(repo, cmd, env=None):
        if cmd[:2] == ["git", "merge-base"]:
            return MagicMock(returncode=0)
        if cmd[:2] == ["git", "push"]:
            return MagicMock(returncode=1, stderr="! [rejected] non-fast-forward", stdout="")
        return MagicMock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(remote_mod, "_git_run", run)

    out = remote_mod.push_repair_fast_forward(
        repo_workspace=ws,
        agent_branch="agent/run-1",
        expected_remote_sha="abc",
        repository="o/r",
        repo_url="https://git.example.com/o/r.git",
        settings=_settings(),
        gitea_client=client,
    )
    assert out["ok"] is False
    assert out["stale"] is True
    assert out["reason"] == "push_rejected"
