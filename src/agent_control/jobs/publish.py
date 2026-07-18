"""RQ job entry for CT103 publish-broker (publish queue only)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_control.config import get_settings
from agent_control.publish.broker import broker_publish_fix, broker_publish_repair


def process_publish(job_payload: dict[str, Any]) -> dict[str, Any]:
    """Job payload may only contain ids — never worker-supplied clone URL or push ref."""
    settings = get_settings()
    state_root = Path(job_payload.get("state_root") or settings.agent_state_root)
    run_id = job_payload["run_id"]
    bundle_id = job_payload["bundle_id"]
    kind = job_payload["kind"]
    attempt_id = job_payload.get("attempt_id", "1")

    if kind == "fix":
        return broker_publish_fix(
            state_root=state_root,
            run_id=run_id,
            attempt_id=attempt_id,
            bundle_id=bundle_id,
            settings=settings,
        )
    if kind == "repair":
        return broker_publish_repair(
            state_root=state_root,
            run_id=run_id,
            attempt_id=attempt_id,
            bundle_id=bundle_id,
            expected_head_commit_sha=job_payload["expected_head_commit_sha"],
            agent_branch=job_payload["agent_branch"],
            project=job_payload["project"],
            allowed_files=list(job_payload.get("allowed_files") or []),
            settings=settings,
        )
    return {"ok": False, "reason": "unknown_kind"}
