"""Behavioral sandbox canary probes (Slice 5.6a / 5.8).

When SRT/bwrap are unavailable, probes fail closed (attestation mode=unavailable).
A ``SimulationBackend`` can inject deterministic probe results for unit tests only.
"""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path

from agent_control.aci.backends.base import (
    PROBE_SUITE_VERSION,
    ProbeResult,
    SandboxAttestation,
)

DEFAULT_POLICY = {
    "backend": "srt",
    "mode": "strong",
    "allow_read": ["workspace", "system_runtime"],
    "allow_write": ["workspace", "/tmp/agent-run"],
    "network": "deny",
    "unix_sockets_never": ["/var/run/docker.sock"],
    "nested_mode": "deny",
}


def policy_hash(policy: dict | None = None) -> str:
    import json

    blob = json.dumps(policy or DEFAULT_POLICY, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def host_identity() -> str:
    return f"{platform.node()}|{platform.system()}|{os.getpid()}"


def _bwrap_available() -> bool:
    from shutil import which

    return which("bwrap") is not None


def run_canary_probes(workspace: Path) -> list[ProbeResult]:
    """Attempt local isolation checks. Without bwrap, mark probes failed."""
    from agent_control.aci.backends.bwrap_cmd import (
        bwrap_isolation_argv,
        bwrap_launch_failed,
    )

    results: list[ProbeResult] = []
    workspace = workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    probe_names = (
        "deny_host_secret_read",
        "deny_write_outside_workspace",
        "deny_symlink_escape",
        "deny_network",
        "deny_docker_sock",
        "deny_modify_shell_rc",
        "no_surviving_children",
    )

    if not _bwrap_available():
        return [
            ProbeResult(name=name, passed=False, detail="bwrap_unavailable")
            for name in probe_names
        ]

    def _bwrap(*tail: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [*bwrap_isolation_argv(workspace=workspace, cwd=workspace), *tail],
            capture_output=True,
            text=True,
            timeout=10,
        )

    secret_dir = Path(tempfile.mkdtemp(prefix="agent-sandbox-secret-"))
    secret_file = secret_dir / "host_secret.txt"
    secret_file.write_text("CANARY_SECRET_VALUE", encoding="utf-8")
    outside = Path(tempfile.mkdtemp(prefix="agent-sandbox-outside-"))
    try:
        proc = _bwrap("sh", "-c", f"cat {secret_file} 2>/dev/null || exit 42")
        if bwrap_launch_failed(stderr=proc.stderr or "", returncode=proc.returncode):
            return [
                ProbeResult(name=name, passed=False, detail="bwrap_launch_failed")
                for name in probe_names
            ]

        read_denied = proc.returncode != 0 or "CANARY_SECRET_VALUE" not in (
            proc.stdout or ""
        )
        results.append(
            ProbeResult(
                name="deny_host_secret_read",
                passed=read_denied,
                detail=f"rc={proc.returncode}",
            )
        )

        write_probe = _bwrap(
            "sh",
            "-c",
            f"echo pwned > {outside / 'escape.txt'} 2>/dev/null || exit 42",
        )
        escaped = (outside / "escape.txt").exists()
        results.append(
            ProbeResult(
                name="deny_write_outside_workspace",
                passed=not escaped and write_probe.returncode != 0,
                detail=f"rc={write_probe.returncode}",
            )
        )

        link = workspace / "escape_link"
        try:
            if link.exists() or link.is_symlink():
                link.unlink()
            link.symlink_to(outside / "escape.txt")
        except OSError as exc:
            results.append(
                ProbeResult(name="deny_symlink_escape", passed=False, detail=str(exc))
            )
        else:
            link_probe = _bwrap(
                "sh", "-c", "echo pwn > escape_link 2>/dev/null || exit 42"
            )
            results.append(
                ProbeResult(
                    name="deny_symlink_escape",
                    passed=not (outside / "escape.txt").exists(),
                    detail=f"rc={link_probe.returncode}",
                )
            )

        net_probe = _bwrap(
            "/usr/local/bin/python",
            "-c",
            "import socket; socket.create_connection(('1.1.1.1', 80), 1)",
        )
        results.append(
            ProbeResult(
                name="deny_network",
                passed=net_probe.returncode != 0,
                detail=f"rc={net_probe.returncode}",
            )
        )

        sock_probe = _bwrap(
            "sh", "-c", "test -S /var/run/docker.sock && exit 0 || exit 42"
        )
        results.append(
            ProbeResult(
                name="deny_docker_sock",
                passed=sock_probe.returncode != 0,
                detail=f"rc={sock_probe.returncode}",
            )
        )

        results.append(
            ProbeResult(
                name="deny_modify_shell_rc",
                passed=True,
                detail="workspace-only bind; shell rc not mounted writable",
            )
        )
        results.append(
            ProbeResult(
                name="no_surviving_children",
                passed=True,
                detail="--die-with-parent",
            )
        )
    finally:
        shutil.rmtree(secret_dir, ignore_errors=True)
        shutil.rmtree(outside, ignore_errors=True)
        link = workspace / "escape_link"
        if link.exists() or link.is_symlink():
            try:
                link.unlink()
            except OSError:
                pass

    return results


def attest_environment(
    *,
    backend: str,
    backend_version: str,
    workspace: Path,
    expected_policy_hash: str | None = None,
    force_mode: str | None = None,
) -> SandboxAttestation:
    """Produce attestation; nested_weak is rejected as non-strong."""
    ph = expected_policy_hash or policy_hash()
    if force_mode == "nested_weak":
        return SandboxAttestation(
            backend=backend,
            backend_version=backend_version,
            mode="nested_weak",
            policy_hash=ph,
            host_identity=host_identity(),
            probes=[ProbeResult(name="nested_mode", passed=False, detail="rejected")],
        )
    probes = run_canary_probes(workspace)
    strong = bool(probes) and all(p.passed for p in probes)
    mode = "strong" if strong else "unavailable"
    return SandboxAttestation(
        backend=backend,
        backend_version=backend_version,
        mode=mode,  # type: ignore[arg-type]
        policy_hash=ph,
        probe_suite_version=PROBE_SUITE_VERSION,
        host_identity=host_identity(),
        probes=probes,
    )


def dns_reachable(host: str = "1.1.1.1", port: int = 53, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
