"""Credential / import boundary tests (V4.1.1)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from agent_workers.settings import WorkerCredentialError, get_worker_settings

ROOT = Path(__file__).resolve().parents[1] / "src" / "agent_workers"

FORBIDDEN_IMPORT_SUBSTRINGS = (
    "agent_control.publish.remote",
    "agent_control.publish.broker",
    "GiteaClient",
)


def test_ct104_startup_fails_with_write_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITEA_BOT_TOKEN", "secret-token")
    monkeypatch.delenv("CT104_ALLOW_WRITE_TOKEN_DEBT", raising=False)
    with pytest.raises(WorkerCredentialError):
        get_worker_settings()


def test_ct104_startup_ok_without_write_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITEA_BOT_TOKEN", raising=False)
    monkeypatch.delenv("GITEA_AGENT_TOKEN", raising=False)
    monkeypatch.delenv("CT104_ALLOW_WRITE_TOKEN_DEBT", raising=False)
    settings = get_worker_settings()
    assert settings.gitea_bot_token == ""
    assert settings.gitea_agent_token == ""


def test_worker_remote_publish_raises() -> None:
    from agent_workers.publish import remote as remote_mod

    with pytest.raises(RuntimeError, match="V4.1.1"):
        remote_mod.publish_fix_branch_and_pr()
    with pytest.raises(RuntimeError, match="V4.1.1"):
        remote_mod.push_repair_fast_forward()


def test_no_worker_imports_publish_broker_mutation() -> None:
    """Fail if agent_workers modules import CT103 publish mutation entrypoints."""
    offenders: list[str] = []
    banned_modules = {
        "agent_control.publish.remote",
        "agent_control.publish.broker",
        "agent_control.publish.validate",
    }
    for path in ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in banned_modules:
                offenders.append(f"{path}: from {node.module}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in banned_modules:
                        offenders.append(f"{path}: import {alias.name}")
    assert not offenders, "Forbidden imports:\n" + "\n".join(offenders)
