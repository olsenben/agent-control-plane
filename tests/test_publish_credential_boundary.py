"""Credential / import boundary tests (V4.1.1) and TB2 fail-closed assertion."""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from agent_control.cli import main
from agent_workers.settings import (
    FORBIDDEN_DURABLE_ENV_NAMES,
    FORBIDDEN_DURABLE_ENV_PREFIXES,
    WORKER_DURABLE_CREDENTIALS_PRESENT,
    WorkerCredentialError,
    assert_ct104_worker_process_credentials,
    assert_worker_durable_credentials_absent,
    collect_durable_credential_violations,
    get_worker_settings,
)

ROOT = Path(__file__).resolve().parents[1] / "src" / "agent_workers"
COMPOSE_CT104 = Path(__file__).resolve().parents[1] / "docker-compose.ct104.yml"

COMPOSE_UNSET_NAMES = (
    *FORBIDDEN_DURABLE_ENV_NAMES,
    "CT104_ALLOW_WRITE_TOKEN_DEBT",
)

TB2_TOKENS = (
    "GITEA_BOT_TOKEN",
    "GITEA_AGENT_TOKEN",
    "BROKER_SIGNING_SECRET",
    "DURABLE_CAPABILITY_SIGNING_SECRET",
    "GITEA_WEBHOOK_SECRET",
    "AGENTFACTS_SIGNING_SECRET",
    "OBSERVE_SHARED_TOKEN",
    "OBSERVE_OAUTH_CLIENT_SECRET",
    "DEPLOY_SSH_KEY",
)


def _clear_durable_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WORKER_DURABLE_CREDENTIALS_PRESENT", raising=False)
    monkeypatch.delenv("CT104_ALLOW_WRITE_TOKEN_DEBT", raising=False)
    for name in FORBIDDEN_DURABLE_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    for key in list(os.environ):
        if any(key.startswith(prefix) for prefix in FORBIDDEN_DURABLE_ENV_PREFIXES):
            monkeypatch.delenv(key, raising=False)


def test_ct104_startup_fails_with_write_token(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_durable_env(monkeypatch)
    monkeypatch.setenv("GITEA_BOT_TOKEN", "secret-token")
    with pytest.raises(WorkerCredentialError, match="GITEA_BOT_TOKEN"):
        get_worker_settings()


def test_ct104_startup_ok_without_write_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_durable_env(monkeypatch)
    settings = get_worker_settings()
    assert settings.gitea_bot_token == ""
    assert settings.gitea_agent_token == ""


def test_write_token_debt_bypass_is_not_honored(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_durable_env(monkeypatch)
    monkeypatch.setenv("GITEA_BOT_TOKEN", "secret-token")
    monkeypatch.setenv("CT104_ALLOW_WRITE_TOKEN_DEBT", "1")
    with pytest.raises(WorkerCredentialError, match="GITEA_BOT_TOKEN"):
        get_worker_settings()


@pytest.mark.parametrize("env_name", TB2_TOKENS)
def test_tb2_worker_fails_closed_on_durable_tokens(
    monkeypatch: pytest.MonkeyPatch, env_name: str
) -> None:
    """TB2-equivalent: worker must not access broker / capability / Gitea write tokens."""
    _clear_durable_env(monkeypatch)
    monkeypatch.setenv(env_name, "must-not-reach-worker")
    with pytest.raises(WorkerCredentialError, match=env_name):
        assert_worker_durable_credentials_absent()
    with pytest.raises(WorkerCredentialError, match=env_name):
        get_worker_settings()


def test_tb2_deploy_prefix_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_durable_env(monkeypatch)
    monkeypatch.setenv("DEPLOY_ANY_CREDENTIAL", "secret")
    with pytest.raises(WorkerCredentialError, match="DEPLOY_ANY_CREDENTIAL"):
        assert_worker_durable_credentials_absent()


def test_flag_not_no_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_durable_env(monkeypatch)
    monkeypatch.setenv("WORKER_DURABLE_CREDENTIALS_PRESENT", "YES")
    with pytest.raises(WorkerCredentialError, match="WORKER_DURABLE_CREDENTIALS_PRESENT"):
        assert_worker_durable_credentials_absent()


def test_git_credentials_does_not_satisfy_write_token_absence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _clear_durable_env(monkeypatch)
    creds = tmp_path / ".git-credentials"
    creds.write_text("https://user:clone-only@git.example.invalid\n", encoding="utf-8")
    monkeypatch.setattr(
        "agent_workers.settings.GIT_CREDENTIALS_CLONE_ONLY_PATH",
        creds,
    )
    monkeypatch.setenv("GITEA_BOT_TOKEN", "write-token")
    with pytest.raises(WorkerCredentialError, match="GITEA_BOT_TOKEN"):
        assert_worker_durable_credentials_absent()


def test_git_credentials_clone_only_ok_without_env_tokens(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _clear_durable_env(monkeypatch)
    creds = tmp_path / ".git-credentials"
    creds.write_text("https://user:clone-only@git.example.invalid\n", encoding="utf-8")
    monkeypatch.setattr(
        "agent_workers.settings.GIT_CREDENTIALS_CLONE_ONLY_PATH",
        creds,
    )
    settings = get_worker_settings()
    assert settings.gitea_bot_token == ""
    assert collect_durable_credential_violations() == []


def test_worker_run_invokes_assertion_for_ct104_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_durable_env(monkeypatch)
    monkeypatch.setenv("BROKER_SIGNING_SECRET", "broker-secret")
    def _must_not_start(*_a: object, **_k: object) -> None:
        raise AssertionError("must not start")

    monkeypatch.setattr("agent_control.cli.run_worker", _must_not_start)
    runner = CliRunner()
    result = runner.invoke(main, ["worker", "run", "--queues", "rlm-root", "--concurrency", "1"])
    assert result.exit_code != 0
    assert "BROKER_SIGNING_SECRET" in result.output


def test_worker_run_starts_when_durable_credentials_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_durable_env(monkeypatch)
    monkeypatch.setenv("WORKER_DURABLE_CREDENTIALS_PRESENT", WORKER_DURABLE_CREDENTIALS_PRESENT)
    started: list[tuple[str, ...]] = []

    def _fake_run_worker(redis_url: str, queues: tuple[str, ...], concurrency: int = 1) -> None:
        started.append(queues)

    monkeypatch.setattr("agent_control.cli.run_worker", _fake_run_worker)
    runner = CliRunner()
    result = runner.invoke(main, ["worker", "run", "--queues", "rlm-root", "--concurrency", "1"])
    assert result.exit_code == 0, result.output
    assert started == [("rlm-root",)]


def test_ct103_publish_queue_skips_assertion_without_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_durable_env(monkeypatch)
    monkeypatch.setenv("GITEA_BOT_TOKEN", "ct103-broker-token")
    assert_ct104_worker_process_credentials(("publish",))


def test_ct104_compose_unsets_durable_tokens() -> None:
    text = COMPOSE_CT104.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    assert data["x-ct104-fail-closed-env"]["WORKER_DURABLE_CREDENTIALS_PRESENT"] == "NO"
    for name in COMPOSE_UNSET_NAMES:
        assert name in text
        assert data["x-ct104-fail-closed-env"][name] is None
    for svc_name, svc in data["services"].items():
        env = svc["environment"]
        # Compose merge keys may remain as <<; also accept explicit keys.
        merged = dict(data["x-ct104-fail-closed-env"])
        if isinstance(env, dict):
            merged.update({k: v for k, v in env.items() if k != "<<"})
        assert merged["WORKER_DURABLE_CREDENTIALS_PRESENT"] == "NO"
        for name in COMPOSE_UNSET_NAMES:
            assert merged.get(name) is None, f"{svc_name} must unset {name}"
        assert "<<: *ct104-fail-closed-env" in text


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
