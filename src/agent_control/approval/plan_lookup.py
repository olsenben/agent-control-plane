"""Resolve plan runs from the event ledger for approval scoping."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from agent_control.config import get_settings
from agent_control.events import load_project_events
from agent_control.project_identity import canonical_project
from agent_control.queue import enqueue_ingest_inbox_file
from agent_control.results_ingest import ct104_inbox_dir, inbox_content_hash
from agent_shared.approval_ids import derive_approval_target_id, derive_plan_alias, parse_approval_target
from agent_shared.hash_utils import hash_blast_radius, hash_plan_result
from agent_shared.models.context_pack import ContextPack
from agent_shared.models.events import AgentRunCompletedEvent
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
    resolution_source: Literal["ledger", "inbox_fallback"] = "ledger"
    inbox_path: str | None = None
    ingest_job_id: str | None = None


def _plan_record_from_payload(
    payload: dict[str, Any],
    project: str,
    *,
    resolution_source: Literal["ledger", "inbox_fallback"] = "ledger",
    inbox_path: str | None = None,
) -> PlanRunRecord | None:
    if payload.get("command_kind") != "plan":
        return None
    issue_id = payload.get("issue_id")
    run_id = payload.get("run_id")
    raw_plan = payload.get("plan_result")
    if issue_id is None or not run_id or raw_plan is None:
        return None
    plan = PlanResult.model_validate(raw_plan)
    blast_hash = payload.get("blast_radius_hash")
    if not blast_hash:
        pack_raw = payload.get("context_pack")
        if pack_raw:
            pack = ContextPack.model_validate(pack_raw)
            blast_hash = hash_blast_radius(pack.blast_radius)
        else:
            blast_hash = hash_blast_radius(plan.blast_radius)
    return PlanRunRecord(
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
        resolution_source=resolution_source,
        inbox_path=inbox_path,
    )


def _plan_runs_from_events(events: list[dict[str, Any]], project: str) -> list[PlanRunRecord]:
    records: list[PlanRunRecord] = []
    for event in events:
        if event.get("type") != "agent.run_completed":
            continue
        payload = event.get("payload") or {}
        record = _plan_record_from_payload(payload, project, resolution_source="ledger")
        if record is not None:
            records.append(record)
    return records


def _plan_runs_from_inbox(
    state_root: Path,
    project: str,
    *,
    issue_id: int | None = None,
) -> list[PlanRunRecord]:
    inbox = ct104_inbox_dir(state_root)
    if not inbox.is_dir():
        return []
    records: list[PlanRunRecord] = []
    for path in sorted(inbox.glob("*.json")):
        if path.name.endswith(".processed"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            event_model = AgentRunCompletedEvent.model_validate(data)
            payload = event_model.model_dump(mode="json")
        except (json.JSONDecodeError, OSError, ValueError):
            continue
        record = _plan_record_from_payload(
            payload,
            project,
            resolution_source="inbox_fallback",
            inbox_path=str(path),
        )
        if record is None:
            continue
        if issue_id is not None and record.issue_id != issue_id:
            continue
        records.append(record)
    return records


def _trigger_ingest_repair(inbox_path: str, run_id: str) -> str | None:
    settings = get_settings()
    path = Path(inbox_path)
    if not path.is_file():
        return None
    content_hash = inbox_content_hash(path)
    try:
        return enqueue_ingest_inbox_file(
            settings.redis_url,
            run_id,
            inbox_path,
            content_hash,
            str(settings.agent_state_root),
        )
    except Exception:
        from agent_control.jobs.ingest import process_ingest_inbox_file

        process_ingest_inbox_file(str(settings.agent_state_root), inbox_path)
        return "inline"


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


def _match_records_for_target(
    records: list[PlanRunRecord],
    target: str,
    issue_id: int,
) -> list[PlanRunRecord]:
    parsed = parse_approval_target(target)
    if parsed is None:
        raise PlanResolutionError(f"Invalid approval target: {target}", code="invalid_target")

    kind, wi_issue, suffix = parsed
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
    if record.issue_id != issue_id:
        raise PlanResolutionError("Plan issue mismatch", code="issue_mismatch")
    return [record]


def resolve_plan_for_target(
    state_root,
    project: str,
    issue_id: int,
    target: str,
) -> PlanRunRecord:
    ledger_records = list_plan_runs(state_root, project, issue_id=issue_id)
    if ledger_records:
        return _match_records_for_target(ledger_records, target, issue_id)[0]

    inbox_records = _plan_runs_from_inbox(Path(state_root), project, issue_id=issue_id)
    if not inbox_records:
        raise PlanResolutionError("No plan run found for this issue", code="no_plan")

    record = _match_records_for_target(inbox_records, target, issue_id)[0]
    ingest_job_id = None
    if record.inbox_path:
        ingest_job_id = _trigger_ingest_repair(record.inbox_path, record.run_id)
    return PlanRunRecord(
        project=record.project,
        issue_id=record.issue_id,
        run_id=record.run_id,
        approval_target_id=record.approval_target_id,
        plan_alias=record.plan_alias,
        plan_result=record.plan_result,
        plan_hash=record.plan_hash,
        blast_radius_hash=record.blast_radius_hash,
        allowed_files=record.allowed_files,
        resolution_source="inbox_fallback",
        inbox_path=record.inbox_path,
        ingest_job_id=ingest_job_id,
    )
