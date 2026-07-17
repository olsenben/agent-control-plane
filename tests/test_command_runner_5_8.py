"""Tests for Slice 5.8 command_runner + registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_control.aci.backends.base import CommandResult, ProbeResult, SandboxAttestation
from agent_control.aci.backends.probes import policy_hash
from agent_control.config import Settings
from agent_control.sandbox import command_runner as cr


@pytest.fixture
def registry_file(tmp_path: Path) -> Path:
    path = tmp_path / "command_registry.yaml"
    path.write_text(
        """
commands:
  echo_ok:
    argv: ["echo", "hi"]
    cwd: repo_root
    timeout_seconds: 5
    environment_allowlist: ["PATH", "HOME"]
    max_output_bytes: 1024
  bad_cwd:
    argv: ["echo", "x"]
    cwd: ../../etc
    timeout_seconds: 5
    environment_allowlist: ["PATH"]
    max_output_bytes: 1024
failure_class_commands:
  test_failure: [echo_ok]
""",
        encoding="utf-8",
    )
    return path


def test_unknown_command_id_rejected(registry_file: Path, tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    settings = Settings(SANDBOX_BACKEND="deny")
    result = cr.run_registered_command(
        "nope",
        workspace=ws,
        settings=settings,
        registry_path=registry_file,
    )
    assert result.violated
    assert "registry_rejected" in result.violation_codes


def test_extra_argv_forbidden(registry_file: Path, tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    with pytest.raises(ValueError, match="caller_argv_forbidden"):
        cr.run_registered_command(
            "echo_ok",
            workspace=ws,
            registry_path=registry_file,
            extra_argv=["--extra"],
        )


def test_cwd_traversal_rejected(registry_file: Path, tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    settings = Settings(SANDBOX_BACKEND="deny")
    result = cr.run_registered_command(
        "bad_cwd",
        workspace=ws,
        settings=settings,
        registry_path=registry_file,
    )
    assert result.violated
    assert "registry_rejected" in result.violation_codes


def test_deny_backend_never_executes(registry_file: Path, tmp_path: Path, monkeypatch) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    settings = Settings(
        SANDBOX_BACKEND="deny",
        SANDBOX_EXPECTED_POLICY_HASH=policy_hash(),
    )
    ran = {"n": 0}

    class Boom:
        name = "deny"

        def attest(self, *, workspace, policy_hash=None):
            return SandboxAttestation(
                backend="deny",
                backend_version="0",
                mode="deny",
                policy_hash=policy_hash or "",
                probes=[ProbeResult(name="deny", passed=False)],
            )

        def run(self, *args, **kwargs):
            ran["n"] += 1
            return CommandResult(0, "", "")

    monkeypatch.setattr(cr, "get_sandbox_backend", lambda *a, **k: Boom())
    result = cr.run_registered_command(
        "echo_ok",
        workspace=ws,
        settings=settings,
        registry_path=registry_file,
    )
    assert result.violated
    assert "sandbox_check_failed" in result.violation_codes
    assert ran["n"] == 0


def test_strong_path_uses_backend_run(registry_file: Path, tmp_path: Path, monkeypatch) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    settings = Settings(
        SANDBOX_BACKEND="srt",
        SANDBOX_EXPECTED_POLICY_HASH=policy_hash(),
    )
    att = SandboxAttestation(
        backend="srt",
        backend_version="test",
        mode="strong",
        policy_hash=policy_hash(),
        probes=[ProbeResult(name="canary", passed=True)],
    )

    class Fake:
        name = "srt"

        def attest(self, *, workspace, policy_hash=None):
            return att

        def run(self, argv, *, cwd, workspace, timeout_seconds, env=None):
            assert env is not None
            assert "GITEA_BOT_TOKEN" not in env
            return CommandResult(0, "hi\n", "")

    monkeypatch.setattr(cr, "get_sandbox_backend", lambda *a, **k: Fake())
    result = cr.run_registered_command(
        "echo_ok",
        workspace=ws,
        settings=settings,
        registry_path=registry_file,
    )
    assert result.exit_code == 0
    assert not result.violated
    assert result.attestation is att
    assert result.session_id
    assert result.stdout.startswith("hi")


def test_failure_class_mapping(registry_file: Path) -> None:
    ids = cr.required_command_ids_for_failure_class(
        "test_failure",
        registry_path=registry_file,
    )
    assert ids == ["echo_ok"]


def test_aci_run_command_requires_workspace() -> None:
    from agent_control.aci.tools import run_command

    out = run_command("echo_ok", cwd=None)
    assert out["violated"] is True
