"""Disposable workspace sandbox — wraps SandboxBackend attestation."""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import TracebackType

from agent_control.aci.backends import SandboxAttestation, get_sandbox_backend
from agent_control.aci.backends.probes import policy_hash
from agent_control.config import Settings, get_settings


class Sandbox:
    """Context manager for a disposable workspace plus startup attestation."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._tmpdir: tempfile.TemporaryDirectory[str] | None = None
        self.root: Path | None = None
        self.attestation: SandboxAttestation | None = None

    def __enter__(self) -> Path:
        self._tmpdir = tempfile.TemporaryDirectory(prefix="agent-sandbox-")
        self.root = Path(self._tmpdir.name)
        backend = get_sandbox_backend(
            self.settings.sandbox_backend,
            expected_policy_hash=self.settings.sandbox_expected_policy_hash or None,
        )
        ph = self.settings.sandbox_expected_policy_hash or policy_hash()
        self.attestation = backend.attest(workspace=self.root, policy_hash=ph)
        return self.root

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._tmpdir:
            self._tmpdir.cleanup()
        self.root = None

    @property
    def sandbox_ready(self) -> bool:
        return bool(self.attestation and self.attestation.strong_ok)
