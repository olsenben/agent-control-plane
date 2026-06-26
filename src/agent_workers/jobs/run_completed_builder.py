"""Build enriched AgentRunCompletedEvent for CT103 inbox ingest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from agent_shared.hash_utils import hash_blast_radius, hash_plan_result
from agent_shared.models.events import AgentRunCompletedEvent, RiskTagSourceEntry
from agent_shared.models.fix import FixResult
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
    fix_result: FixResult | None = None,
) -> tuple[list[str], list[RiskTagSourceEntry]]:
    tags: set[str] = set()
    if command_kind == "review" and review_result is not None:
        tags.update(review_result.risk_tags)
        for finding in review_result.findings:
            tags.update(finding.risk_tags)
    elif command_kind == "plan" and plan_result is not None:
        tags.update(plan_result.risk_tags)
    elif command_kind == "fix" and fix_result is not None:
        tags.update(fix_result.risk_tags)
    sorted_tags = sorted(tags)
    sources = [RiskTagSourceEntry(tag=tag, source="model_output") for tag in sorted_tags]
    return sorted_tags, sources


def _load_diff_gate_result(artifact_root: Path) -> dict[str, Any] | None:
    path = artifact_root / "diff_gate_result.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _gate_policy_tags(gate: dict[str, Any] | None) -> tuple[list[str], list[RiskTagSourceEntry]]:
    if not gate or gate.get("passed"):
        return [], []
    codes = gate.get("violations") or []
    tags = sorted({str(v.get("code")) for v in codes if v.get("code")})
    sources = [RiskTagSourceEntry(tag=tag, source="policy_gate") for tag in tags]
    if "secret_exposure" in tags and "secret_exposure" not in {s.tag for s in sources}:
        pass
    extra_tags: list[str] = []
    if "secret_exposure" in tags:
        extra_tags.append("secret_exposure")
    merged_tags = sorted(set(tags) | set(extra_tags))
    merged_sources = [RiskTagSourceEntry(tag=tag, source="policy_gate") for tag in merged_tags]
    return merged_tags, merged_sources


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
    fix_result: FixResult | None = None
    raw_review = result.get("review_result")
    raw_plan = result.get("plan_result")
    raw_fix = result.get("fix_result")
    if command_kind == "review" and raw_review is not None:
        review_result = ReviewResult.model_validate(raw_review)
    elif command_kind == "plan" and raw_plan is not None:
        plan_result = PlanResult.model_validate(raw_plan)
    elif command_kind == "fix" and raw_fix is not None:
        fix_result = FixResult.model_validate(raw_fix)

    context_sources = _load_context_sources(artifact_root, job)
    prompt_hash, prompt_hash_source = extract_prompt_hash_from_trace(artifact_root / "rlm_trace.jsonl")
    summary_hash = sha256_text(summary) if summary else None
    risk_tags, risk_tag_sources = collect_risk_tags(
        command_kind=command_kind,
        review_result=review_result,
        plan_result=plan_result,
        fix_result=fix_result,
    )

    diff_gate = result.get("diff_gate_result") or _load_diff_gate_result(artifact_root)
    gate_tags, gate_sources = _gate_policy_tags(diff_gate)
    if gate_tags:
        merged_tags = sorted(set(risk_tags) | set(gate_tags))
        source_by_tag = {s.tag: s for s in risk_tag_sources}
        for gs in gate_sources:
            source_by_tag[gs.tag] = gs
        risk_tags = merged_tags
        risk_tag_sources = [source_by_tag[t] for t in risk_tags]

    plan_hash: str | None = None
    blast_radius_hash: str | None = None
    approval_target_id: str | None = None
    plan_alias: str | None = None
    approval_id: str | None = None
    diff_gate_passed: bool | None = None
    diff_gate_violation_codes: list[str] = []
    diff_gate_policy_sources: list[str] = []
    policy_decision: str = "allow"

    if diff_gate is not None:
        diff_gate_passed = bool(diff_gate.get("passed"))
        diff_gate_violation_codes = [
            str(v.get("code"))
            for v in (diff_gate.get("violations") or [])
            if v.get("code")
        ]
        diff_gate_policy_sources = list(diff_gate.get("policy_sources") or [])
        approval_id = diff_gate.get("approval_id")

    run_status = result.get("status", "completed")
    terminal_status = result.get("terminal_status")
    if not terminal_status:
        terminal_status = "completed" if run_status == "completed" else "failed_infra"

    if command_kind == "fix" and run_status == "failed":
        policy_decision = "deny"
    elif diff_gate is not None and not diff_gate.get("passed"):
        policy_decision = "deny"
    elif run_status == "failed":
        policy_decision = "deny"

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
    elif command_kind == "fix":
        binding = job.get("fix_authorization") or {}
        approval_target_id = binding.get("approval_target_id")
        approval_id = approval_id or binding.get("approval_id")
        plan_hash = binding.get("plan_hash")
        blast_radius_hash = binding.get("blast_radius_hash")
        if binding.get("plan_run_id"):
            plan_alias = derive_plan_alias(str(binding["plan_run_id"]))

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
        status=run_status,
        terminal_status=terminal_status,
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
        fix_result=fix_result if command_kind == "fix" else None,
        patch_path=result.get("patch_path") if run_status == "completed" else None,
        context_sources=context_sources,
        prompt_hash=prompt_hash,
        prompt_hash_source=prompt_hash_source,  # type: ignore[arg-type]
        summary_hash=summary_hash,
        engine=result.get("engine"),
        model_policy=job.get("model_policy"),
        risk_tags=risk_tags,
        risk_tag_sources=risk_tag_sources,
        policy_decision=policy_decision,  # type: ignore[arg-type]
        approval_target_id=approval_target_id,
        plan_alias=plan_alias,
        plan_hash=plan_hash,
        blast_radius_hash=blast_radius_hash,
        diff_gate_passed=diff_gate_passed,
        diff_gate_violation_codes=diff_gate_violation_codes,
        diff_gate_policy_sources=diff_gate_policy_sources,
        approval_id=approval_id,
    )
    return event


def _kind_from_flow(flow: str | None) -> str | None:
    if flow == "code_review":
        return "review"
    if flow == "planner":
        return "plan"
    if flow == "developer":
        return "fix"
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
