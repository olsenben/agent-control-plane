"""Anthropic SRT / Bubblewrap sandbox backend (fail closed)."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from agent_control.aci.backends.base import (
    CommandResult,
    SandboxAttestation,
)
from agent_control.aci.backends.probes import attest_environment, policy_hash

logger = logging.getLogger(__name__)

SRT_PINNED_VERSION = "srt-pin-pending"  # filled after CT104 spike records real version


class DenySandboxBackend:
    """Always deny — used when SRT/bwrap cannot attest strong mode."""

    name = "deny"

    def attest(self, *, workspace: Path, policy_hash: str) -> SandboxAttestation:
        from agent_control.aci.backends.base import ProbeResult

        return SandboxAttestation(
            backend=self.name,
            backend_version="0",
            mode="deny",
            policy_hash=policy_hash,
            probes=[ProbeResult(name="deny_backend", passed=False, detail="fallback_deny")],
        )

    def run(
        self,
        argv: list[str],
        *,
        cwd: Path,
        workspace: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        return CommandResult(
            exit_code=126,
            stdout="",
            stderr="sandbox_denied",
            violated=True,
            violation_codes=["sandbox_unavailable"],
        )


class SrtSandboxBackend:
    """Preferred backend: Bubblewrap strong isolation (SRT when installed).

    Nested mode is never selected. If probes fail, callers must treat attestation
    as non-strong and refuse Risk 2 work.
    """

    name = "srt"

    def __init__(self, *, expected_policy_hash: str | None = None) -> None:
        self.expected_policy_hash = expected_policy_hash or policy_hash()
        self.backend_version = _detect_srt_version()

    def attest(self, *, workspace: Path, policy_hash: str | None = None) -> SandboxAttestation:
        ph = policy_hash or self.expected_policy_hash
        return attest_environment(
            backend=self.name,
            backend_version=self.backend_version,
            workspace=workspace,
            expected_policy_hash=ph,
        )

    def run(
        self,
        argv: list[str],
        *,
        cwd: Path,
        workspace: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        attestation = self.attest(workspace=workspace)
        if not attestation.strong_ok:
            return CommandResult(
                exit_code=126,
                stdout="",
                stderr="sandbox_attestation_failed",
                violated=True,
                violation_codes=["sandbox_check_failed"],
            )
        if not shutil.which("bwrap"):
            return CommandResult(
                exit_code=126,
                stdout="",
                stderr="bwrap_missing",
                violated=True,
                violation_codes=["sandbox_unavailable"],
            )
        from agent_control.aci.backends.bwrap_cmd import (
            bwrap_isolation_argv,
            bwrap_launch_failed,
        )

        cmd = [
            *bwrap_isolation_argv(workspace=workspace, cwd=cwd),
            *argv,
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env=env,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return CommandResult(
                exit_code=124,
                stdout="",
                stderr="timeout",
                violated=True,
                violation_codes=["timeout"],
            )
        if bwrap_launch_failed(stderr=proc.stderr or "", returncode=proc.returncode):
            return CommandResult(
                exit_code=126,
                stdout=proc.stdout or "",
                stderr=proc.stderr or "bwrap_launch_failed",
                violated=True,
                violation_codes=["sandbox_unavailable"],
            )
        return CommandResult(
            exit_code=proc.returncode,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
        )


def get_sandbox_backend(
    name: str = "srt",
    *,
    expected_policy_hash: str | None = None,
) -> SrtSandboxBackend | DenySandboxBackend:
    if name in ("srt", "bwrap"):
        return SrtSandboxBackend(expected_policy_hash=expected_policy_hash)
    return DenySandboxBackend()


def _detect_srt_version() -> str:
    for binary in ("sandbox-runtime", "srt", "anthropic-sandbox-runtime"):
        path = shutil.which(binary)
        if path:
            try:
                out = subprocess.run(
                    [path, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                ver = (out.stdout or out.stderr or "").strip().splitlines()
                if ver:
                    return ver[0][:120]
            except (OSError, subprocess.TimeoutExpired):
                pass
            return f"{binary}:present"
    if shutil.which("bwrap"):
        return "bwrap-only"
    return SRT_PINNED_VERSION
