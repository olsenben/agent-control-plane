"""RLM root queue job handler."""

from __future__ import annotations

from typing import Any

from agent_workers.flows.runner import run_flow_session


def process_rlm_root(job_payload: dict[str, Any]) -> dict[str, Any]:
    return run_flow_session(job_payload)
