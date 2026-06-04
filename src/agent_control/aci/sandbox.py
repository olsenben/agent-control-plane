"""Disposable workspace sandbox (stub)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import TracebackType


class Sandbox:
    def __init__(self) -> None:
        self._tmpdir: tempfile.TemporaryDirectory[str] | None = None
        self.root: Path | None = None

    def __enter__(self) -> Path:
        self._tmpdir = tempfile.TemporaryDirectory(prefix="agent-sandbox-")
        self.root = Path(self._tmpdir.name)
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
