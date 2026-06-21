"""Resolve plan runs from the event ledger for approval scoping."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent_control.events import load_project_events
from agent_control.project_identity import canonical_project
from agent_shared.approval_ids import derive_approval_target_id, derive_plan_alias, parse_approval_target
from agent_shared.hash_utils import hash_blast_radius, hash_plan_result
from agent_shared.models.context_pack import ContextPack
from agent_shared.models.plan import PlanResult


@dataclass(frozen=True)
class PlanRunRecord:
    project: str
    issue_id: int
    run_id: str
    approval_target_id: str
    plan_alias: str
    plan_result: PlanResult
    plan_hash: str
    blast_radius_hash: str
    allowed_files: list[str]


def _plan_runs_from_events(events: list[dict[str, Any]], project: str) -> list[PlanRunRecord]:
    records: list[PlanRunRecord] = []
    for event in events:
        if event.get("type") != "agent.run_completed":
            continue
        payload = event.get("payload") or {}
        if payload.get("command_kind") != "plan":
            continue
        issue_id = payload.get("issue_id")
        run_id = payload.get("run_id")
        raw_plan = payload.get("plan_result")
        if issue_id is None or not run_id or raw_plan is None:
            continue
        plan = PlanResult.model_validate(raw_plan)
        blast_hash = payload.get("blast_radius_hash")
        if not blast_hash:
            pack_raw = payload.get("context_pack")
            if pack_raw:
                pack = ContextPack.model_validate(pack_raw)
                blast_hash = hash_blast_radius(pack.blast_radius)
            else:
                blast_hash = hash_blast_radius(plan.blast_radius)
        records.append(
            PlanRunRecord(
                project=canonical_project(project),
                issue_id=int(issue_id),
                run_id=str(run_id),
                approval_target_id=derive_approval_target_id(
                    issue_id=int(issue_id),
                    plan_run_id=str(run_id),
                ),
                plan_alias=derive_plan_alias(str(run_id)),
                plan_result=plan,
                plan_hash=payload.get("plan_hash") or hash_plan_result(plan),
                blast_radius_hash=str(blast_hash),
                allowed_files=_allowed_files_from_plan(plan),
            )
        )
    return records


def _allowed_files_from_plan(plan: PlanResult) -> list[str]:
    files: set[str] = set()
    for step in plan.steps:
        for path in step.files:
            if path:
                files.add(path)
    return sorted(files)


def list_plan_runs(state_root, project: str, *, issue_id: int | None = None) -> list[PlanRunRecord]:
    from pathlib import Path

    events = load_project_events(Path(state_root), canonical_project(project))
    records = _plan_runs_from_events(events, project)
    if issue_id is None:
        return records
    return [r for r in records if r.issue_id == issue_id]


class PlanResolutionError(Exception):
    def __init__(self, message: str, *, code: str = "not_found") -> None:
        super().__init__(message)
        self.code = code


def resolve_plan_for_target(
    state_root,
    project: str,
    issue_id: int,
    target: str,
) -> PlanRunRecord:
    parsed = parse_approval_target(target)
    if parsed is None:
        raise PlanResolutionError(f"Invalid approval target: {target}", code="invalid_target")

    kind, wi_issue, suffix = parsed
    records = list_plan_runs(state_root, project, issue_id=issue_id)
    if not records:
        raise PlanResolutionError("No plan run found for this issue", code="no_plan")

    matches: list[PlanRunRecord] = []
    for record in records:
        if kind == "wi":
            if record.approval_target_id.lower() == target.lower():
                matches.append(record)
        else:
            if record.plan_alias.lower() == target.lower():
                matches.append(record)
            elif record.run_id.lower().endswith(suffix):
                matches.append(record)

    if not matches:
        raise PlanResolutionError(f"No plan matches target {target}", code="not_found")
    if len(matches) > 1:
        raise PlanResolutionError(
            f"Ambiguous plan target {target}; use full WI-* id",
            code="ambiguous",
        )
    record = matches[0]
    if kind == "wi" and wi_issue is not None and record.issue_id != wi_issue:
        raise PlanResolutionError("Approval target issue mismatch", code="issue_mismatch")
    return record
