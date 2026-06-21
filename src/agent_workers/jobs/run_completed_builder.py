"""Build enriched AgentRunCompletedEvent for CT103 inbox ingest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from agent_shared.hash_utils import hash_blast_radius, hash_plan_result
from agent_shared.models.events import AgentRunCompletedEvent, RiskTagSourceEntry
from agent_shared.models.plan import PlanResult
from agent_shared.models.review import ReviewResult
from agent_shared.models.context_pack import ContextPack
from agent_shared.approval_ids import derive_approval_target_id, derive_plan_alias
from agent_shared.repo_identity import normalize_repo_full_name

_MEMORY_KINDS = frozenset({"review", "plan"})


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_prompt_hash_from_trace(trace_path: Path) -> tuple[str | None, str]:
    if not trace_path.is_file():
        return None, "not_available"
    for line in reversed(trace_path.read_text(encoding="utf-8").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("event") == "final_prompt" and event.get("prompt_text"):
            return sha256_text(str(event["prompt_text"])), "final_prompt"
    return None, "not_available"


def collect_risk_tags(
    *,
    command_kind: str | None,
    review_result: ReviewResult | None,
    plan_result: PlanResult | None,
) -> tuple[list[str], list[RiskTagSourceEntry]]:
    tags: set[str] = set()
    if command_kind == "review" and review_result is not None:
        tags.update(review_result.risk_tags)
        for finding in review_result.findings:
            tags.update(finding.risk_tags)
    elif command_kind == "plan" and plan_result is not None:
        tags.update(plan_result.risk_tags)
    sorted_tags = sorted(tags)
    sources = [RiskTagSourceEntry(tag=tag, source="model_output") for tag in sorted_tags]
    return sorted_tags, sources


def build_run_completed_event(
    *,
    run_id: str,
    project: str,
    artifact_root: Path,
    job: dict[str, Any],
    result: dict[str, Any],
    summary: str,
) -> AgentRunCompletedEvent:
    command_intent = job.get("command_intent") or {}
    command_kind = command_intent.get("kind") or _kind_from_flow(result.get("flow") or job.get("flow"))
    trigger_context = job.get("trigger_context") or {}

    review_result: ReviewResult | None = None
    plan_result: PlanResult | None = None
    raw_review = result.get("review_result")
    raw_plan = result.get("plan_result")
    if command_kind == "review" and raw_review is not None:
        review_result = ReviewResult.model_validate(raw_review)
    elif command_kind == "plan" and raw_plan is not None:
        plan_result = PlanResult.model_validate(raw_plan)

    context_sources = _load_context_sources(artifact_root, job)
    prompt_hash, prompt_hash_source = extract_prompt_hash_from_trace(artifact_root / "rlm_trace.jsonl")
    summary_hash = sha256_text(summary) if summary else None
    risk_tags, risk_tag_sources = collect_risk_tags(
        command_kind=command_kind,
        review_result=review_result,
        plan_result=plan_result,
    )

    plan_hash: str | None = None
    blast_radius_hash: str | None = None
    approval_target_id: str | None = None
    plan_alias: str | None = None

    if command_kind == "plan" and plan_result is not None:
        plan_hash = hash_plan_result(plan_result)
        pack_raw = job.get("context_pack")
        if pack_raw:
            pack = ContextPack.model_validate(pack_raw)
            blast_radius_hash = hash_blast_radius(pack.blast_radius)
        else:
            blast_radius_hash = hash_blast_radius(plan_result.blast_radius)
        if trigger_context.get("issue_number") is not None:
            approval_target_id = plan_result.approval_target_id or derive_approval_target_id(
                issue_id=int(trigger_context["issue_number"]),
                plan_run_id=run_id,
            )
            plan_alias = plan_result.plan_alias or derive_plan_alias(run_id)

    repo_full_name = normalize_repo_full_name(project)

    event = AgentRunCompletedEvent(
        run_id=run_id,
        job_id=job.get("job_id", f"rlm-root-{job.get('trigger_event_id', run_id)}"),
        workflow_id=job.get("workflow_id", run_id),
        session_id=job.get("session_id", run_id),
        trigger_event_id=job.get("trigger_event_id", run_id.replace("run-", "")),
        trigger_delivery_id=job.get("trigger_delivery_id"),
        project=project,
        flow=result.get("flow", job.get("flow", "inspect")),
        agent=result.get("agent", job.get("agent", "explainer")),
        risk_class=str(result.get("risk_class", job.get("risk_class", "read_only"))),
        status=result.get("status", "completed"),
        summary=summary,
        artifact_root=str(artifact_root),
        command_kind=command_kind,
        repo_full_name=repo_full_name,
        issue_id=trigger_context.get("issue_number"),
        pr_id=trigger_context.get("pr_number"),
        branch=job.get("task_ref") or job.get("base_ref"),
        commit_sha=job.get("target_sha"),
        review_result=review_result if command_kind in _MEMORY_KINDS else None,
        plan_result=plan_result if command_kind in _MEMORY_KINDS else None,
        context_sources=context_sources,
        prompt_hash=prompt_hash,
        prompt_hash_source=prompt_hash_source,  # type: ignore[arg-type]
        summary_hash=summary_hash,
        engine=result.get("engine"),
        model_policy=job.get("model_policy"),
        risk_tags=risk_tags,
        risk_tag_sources=risk_tag_sources,
        policy_decision="allow",
        approval_target_id=approval_target_id,
        plan_alias=plan_alias,
        plan_hash=plan_hash,
        blast_radius_hash=blast_radius_hash,
    )
    return event


def _kind_from_flow(flow: str | None) -> str | None:
    if flow == "code_review":
        return "review"
    if flow == "planner":
        return "plan"
    if flow == "inspect":
        return "inspect"
    return flow


def _load_context_sources(artifact_root: Path, job: dict[str, Any]) -> list[str]:
    receipt_path = artifact_root / "context_receipt.json"
    if receipt_path.is_file():
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            sources = receipt.get("sources")
            if isinstance(sources, list):
                return [str(s) for s in sources]
        except (json.JSONDecodeError, OSError):
            pass
    pack = job.get("context_pack") or {}
    sources = pack.get("context_sources")
    if isinstance(sources, list):
        return [str(s) for s in sources]
    return []
