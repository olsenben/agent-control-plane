"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agent_control.config import Settings
from agent_control.events import AgentEvent, append_event, deterministic_event_id
from agent_control.graph.snapshot import snapshot_project
from agent_shared.approval_ids import derive_approval_target_id, derive_plan_alias
from agent_shared.hash_utils import hash_blast_radius, hash_plan_result
from agent_shared.models.plan import PlanResult, PlanStep
from agent_shared.models.review import BlastRadiusContext


@pytest.fixture
def control_plane_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def graph_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    state = tmp_path / "agent-state"
    cache = tmp_path / "cache"
    state.mkdir()
    cache.mkdir()
    monkeypatch.setenv("AGENT_STATE_ROOT", str(state))
    monkeypatch.setenv("AGENT_CACHE_DIR", str(cache))
    return Settings()


@pytest.fixture
def indexed_graph(graph_settings: Settings, control_plane_root: Path):
    project = "ai-sdlc-lab/agent-control-plane"
    result = snapshot_project(
        project,
        settings=graph_settings,
        local_path=control_plane_root,
    )
    return graph_settings, result


# --- Approval test helpers (Slice 6A) ---


def sample_plan(*, with_files: bool = True) -> PlanResult:
    files = ["src/agent_control/foo.py"] if with_files else []
    return PlanResult(
        scope_summary="Fix webhook gap",
        steps=[PlanStep(id="S1", summary="Update handler", files=files)],
        blast_radius=BlastRadiusContext(affected_repos=["ai-sdlc-lab/demo-app"]),
        recommended_next_command="/agent fix WI-0004-dc0b71eb",
    )


def seed_plan_completed(
    tmp_path: Path,
    *,
    project: str = "ai-sdlc-lab/agent-control-plane",
    issue_id: int = 4,
    run_id: str = "run-dc0b71ebebb3379b440471e2caa2b9cc",
    plan: PlanResult | None = None,
    pack_blast: BlastRadiusContext | None = None,
) -> str:
    plan = plan or sample_plan()
    plan_hash = hash_plan_result(plan)
    blast = pack_blast or BlastRadiusContext(affected_services=["worker-state"])
    blast_hash = hash_blast_radius(blast)
    target = derive_approval_target_id(issue_id=issue_id, plan_run_id=run_id)
    alias = derive_plan_alias(run_id)
    plan = plan.model_copy(update={"approval_target_id": target, "plan_alias": alias})

    event_id = deterministic_event_id("ct104", run_id, "agent.run_completed")
    payload: dict[str, Any] = {
        "run_id": run_id,
        "command_kind": "plan",
        "issue_id": issue_id,
        "plan_result": plan.model_dump(mode="json"),
        "plan_hash": plan_hash,
        "blast_radius_hash": blast_hash,
        "approval_target_id": target,
        "plan_alias": alias,
        "project": project,
    }
    event = AgentEvent(
        event_id=event_id,
        type="agent.run_completed",
        raw_event_type="agent.run_completed",
        source="ct104",
        delivery_id=run_id,
        project=project,
        payload=payload,
        recorded_at="2026-06-17T12:00:00+00:00",
    )
    append_event(tmp_path, event)
    return target
