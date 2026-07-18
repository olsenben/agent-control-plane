"""Shared bubblewrap argv for SRT backend + canary probes."""

from __future__ import annotations

from pathlib import Path

_LAUNCH_FAIL_MARKERS = (
    "creating new namespace failed",
    "loopback: failed",
    "operation not permitted",
)


def bwrap_isolation_argv(*, workspace: Path, cwd: Path) -> list[str]:
    """Isolation prefix: net unshare, system runtime ro, workspace rw.

    Merged-/usr images need symlinks for /bin and /lib. /usr/local holds
    the worker image's Python and pip-installed verifier tools.
    """
    ws = str(workspace.resolve())
    cd = str(cwd.resolve())
    return [
        "bwrap",
        "--die-with-parent",
        "--unshare-net",
        "--ro-bind",
        "/usr",
        "/usr",
        "--symlink",
        "usr/bin",
        "/bin",
        "--symlink",
        "usr/lib",
        "/lib",
        "--symlink",
        "usr/lib64",
        "/lib64",
        "--ro-bind",
        "/usr/local",
        "/usr/local",
        "--bind",
        ws,
        ws,
        "--tmpfs",
        "/tmp",
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        "--chdir",
        cd,
    ]


def bwrap_launch_failed(*, stderr: str, returncode: int) -> bool:
    """True when bwrap itself could not start (do not treat as deny-success)."""
    del returncode
    text = (stderr or "").lower()
    return any(marker in text for marker in _LAUNCH_FAIL_MARKERS)
