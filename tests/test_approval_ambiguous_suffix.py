"""Ambiguous PLAN-run suffix resolution fails closed."""

from pathlib import Path

import pytest

from agent_control.approval.plan_lookup import PlanResolutionError, resolve_plan_for_target
from agent_control.events import AgentEvent, append_event, deterministic_event_id
from agent_shared.approval_ids import derive_approval_target_id
from agent_shared.hash_utils import hash_blast_radius, hash_plan_result
from conftest import sample_plan


def _seed_run(tmp_path: Path, run_id: str) -> None:
    plan = sample_plan()
    payload = {
        "run_id": run_id,
        "command_kind": "plan",
        "issue_id": 4,
        "plan_result": plan.model_dump(mode="json"),
        "plan_hash": hash_plan_result(plan),
        "blast_radius_hash": hash_blast_radius(plan.blast_radius),
        "approval_target_id": derive_approval_target_id(issue_id=4, plan_run_id=run_id),
    }
    append_event(
        tmp_path,
        AgentEvent(
            event_id=deterministic_event_id("ct104", run_id, "agent.run_completed"),
            type="agent.run_completed",
            project="ai-sdlc-lab/agent-control-plane",
            delivery_id=run_id,
            payload=payload,
            recorded_at="2026-06-17T12:00:00+00:00",
        ),
    )


def test_ambiguous_plan_suffix(tmp_path: Path) -> None:
    _seed_run(tmp_path, "run-aaaaaaaadc0b71eb")
    _seed_run(tmp_path, "run-bbbbbbbbdc0b71eb")
    with pytest.raises(PlanResolutionError) as exc:
        resolve_plan_for_target(tmp_path, "ai-sdlc-lab/agent-control-plane", 4, "PLAN-run-dc0b71eb")
    assert exc.value.code == "ambiguous"
