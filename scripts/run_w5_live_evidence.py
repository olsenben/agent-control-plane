#!/usr/bin/env python3
"""Thin ACP entrypoint for the W5 live-evidence provider integration runner.

Delegates to maintenance-evals/scripts/run_w5_live_evidence_provider_integration.py.
Does not retune C, mint capabilities, or publish Gitea PRs in LOCAL mode.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "maintenance-evals"
    / "scripts"
    / "run_w5_live_evidence_provider_integration.py"
)


def main() -> int:
    if not SCRIPT.is_file():
        print(f"missing runner: {SCRIPT}", file=sys.stderr)
        return 2
    runpy.run_path(str(SCRIPT), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
