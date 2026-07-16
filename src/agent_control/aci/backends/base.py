"""SandboxBackend interface and attestation (Slice 5.8 / ADR-0002)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Protocol

SandboxMode = Literal["strong", "nested_weak", "unavailable", "deny"]

PROBE_SUITE_VERSION = "sandbox_canary.v1"


@dataclass
class ProbeResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class SandboxAttestation:
    backend: str
    backend_version: str
    mode: SandboxMode
    policy_hash: str
    probe_suite_version: str = PROBE_SUITE_VERSION
    host_identity: str = ""
    checked_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    probes: list[ProbeResult] = field(default_factory=list)

    @property
    def strong_ok(self) -> bool:
        return self.mode == "strong" and all(p.passed for p in self.probes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "backend_version": self.backend_version,
            "mode": self.mode,
            "policy_hash": self.policy_hash,
            "probe_suite_version": self.probe_suite_version,
            "host_identity": self.host_identity,
            "checked_at": self.checked_at,
            "probes": [
                {"name": p.name, "passed": p.passed, "detail": p.detail} for p in self.probes
            ],
            "strong_ok": self.strong_ok,
        }


@dataclass
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str
    violated: bool = False
    violation_codes: list[str] = field(default_factory=list)


class SandboxBackend(Protocol):
    name: str

    def attest(self, *, workspace: Path, policy_hash: str) -> SandboxAttestation: ...

    def run(
        self,
        argv: list[str],
        *,
        cwd: Path,
        workspace: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult: ...
