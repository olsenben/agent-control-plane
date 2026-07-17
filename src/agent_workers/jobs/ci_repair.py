"""RQ entrypoint for CI repair jobs (Slice 6F.2)."""

from __future__ import annotations

from typing import Any


def process_ci_repair(job_payload: dict[str, Any]) -> dict[str, Any]:
    from agent_workers.ci_repair import run_ci_repair_job

    return run_ci_repair_job(job_payload)
