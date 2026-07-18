"""Tests for repair fast-forward push helper (CT103 broker)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from agent_control.config import Settings
from agent_control.publish import remote as remote_mod


def _settings() -> Settings:
    s = Settings()
    s.gitea_base_url = "https://git.example.com"
    s.gitea_bot_token = "tok"
    return s


def test_push_repair_stale_when_remote_moved(tmp_path: Path, monkeypatch) -> None:
    ws = tmp_path / "repo"
    ws.mkdir()
    client = MagicMock()
    client.get_branch_sha.return_value = "other"

    out = remote_mod.push_repair_fast_forward(
        workspace=ws,
        commit_sha="newsha",
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


def test_push_repair_parent_mismatch(tmp_path: Path, monkeypatch) -> None:
    ws = tmp_path / "repo"
    ws.mkdir()
    client = MagicMock()
    client.get_branch_sha.return_value = "abc"

    def fake_git(repo, cmd, env=None):
        class R:
            returncode = 0
            stdout = "notparent\n"
            stderr = ""

        return R()

    monkeypatch.setattr(remote_mod, "git_run", fake_git)
    out = remote_mod.push_repair_fast_forward(
        workspace=ws,
        commit_sha="newsha",
        agent_branch="agent/run-1",
        expected_remote_sha="abc",
        repository="o/r",
        repo_url="https://git.example.com/o/r.git",
        settings=_settings(),
        gitea_client=client,
    )
    assert out["ok"] is False
    assert "parent_mismatch" in (out.get("reason_codes") or [])


def test_push_repair_rejects_non_agent_branch(tmp_path: Path) -> None:
    ws = tmp_path / "repo"
    ws.mkdir()
    out = remote_mod.push_repair_fast_forward(
        workspace=ws,
        commit_sha="newsha",
        agent_branch="main",
        expected_remote_sha="abc",
        repository="o/r",
        repo_url="https://git.example.com/o/r.git",
        settings=_settings(),
    )
    assert out["ok"] is False
    assert "branch_policy" in (out.get("reason_codes") or [])
