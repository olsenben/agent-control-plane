"""Map CT104 completed events to memory_record.v1."""

from __future__ import annotations

from datetime import datetime, timezone

from agent_shared.models.events import AgentRunCompletedEvent
from agent_shared.models.memory import (
    MemoryAudit,
    MemoryGovernance,
    MemoryRecord,
    RecommendedNextStep,
    RiskTagSource,
)
from agent_shared.models.plan import PlanResult
from agent_shared.models.review import ReviewResult
from agent_shared.repo_identity import normalize_repo_full_name, split_repo_full_name

_MEMORY_COMMANDS = frozenset({"review", "plan"})


def collect_risk_tags_from_review(review: ReviewResult) -> list[str]:
    tags: set[str] = set(review.risk_tags)
    for finding in review.findings:
        tags.update(finding.risk_tags)
    return sorted(tags)


def collect_risk_tags_from_plan(plan: PlanResult) -> list[str]:
    return sorted(set(plan.risk_tags))


def risk_tag_sources_for_model(tags: list[str]) -> list[RiskTagSource]:
    return [RiskTagSource(tag=tag, source="model_output") for tag in tags]


def policy_gate_risk_tags(event: AgentRunCompletedEvent) -> list[RiskTagSource]:
    """Deterministic policy tags applied at ingest (MVP)."""
    extra: list[RiskTagSource] = []
    if event.command_kind == "review" and event.review_result is not None:
        review = event.review_result
        missing = review.blast_radius.missing_graph_edges or []
        if missing and missing != ["not implemented"]:
            if not any(
                [
                    review.blast_radius.affected_repos,
                    review.blast_radius.affected_services,
                    review.blast_radius.affected_tests,
                    review.blast_radius.related_adrs,
                ]
            ):
                extra.append(RiskTagSource(tag="graph_bypass", source="policy_gate"))
    return extra


def memory_record_from_completed(event: AgentRunCompletedEvent) -> MemoryRecord | None:
    kind = event.command_kind or _command_kind_from_flow(event.flow)
    if kind not in _MEMORY_COMMANDS:
        return None

    repo_full_name = normalize_repo_full_name(event.repo_full_name or event.project)
    if repo_full_name is None:
        return None

    if kind == "review" and event.review_result is None:
        return None
    if kind == "plan" and event.plan_result is None:
        return None

    owner, repo = split_repo_full_name(repo_full_name)
    now = datetime.now(timezone.utc).isoformat()
    model_tags = _model_risk_tags(event, kind)
    gate_tags = policy_gate_risk_tags(event)
    merged_sources = _merge_risk_tag_sources(model_tags, gate_tags)
    all_tags = sorted({s.tag for s in merged_sources})

    record = MemoryRecord(
        record_id=f"mem-{event.run_id}",
        run_id=event.run_id,
        repo_owner=owner,
        repo_name=repo,
        repo_full_name=repo_full_name,
        issue_id=event.issue_id,
        pr_id=event.pr_id,
        branch=event.branch or "main",
        commit_sha=event.commit_sha,
        source_command=kind,  # type: ignore[arg-type]
        source_run_id=event.run_id,
        source_model=event.model_policy,
        source_engine=event.engine,
        source_commit_sha=event.commit_sha,
        confidence=_confidence_for(event, kind),
        memory_quality="model_generated",
        created_at=now,
        updated_at=now,
        governance=MemoryGovernance(
            risk_tags=all_tags,
            risk_tag_sources=merged_sources,
            policy_decision="allow",
            risk_class=_risk_class_int(event.risk_class),
        ),
        audit=MemoryAudit(
            prompt_hash=event.prompt_hash,
            prompt_hash_source=event.prompt_hash_source,
            summary_hash=event.summary_hash,
            context_sources=list(event.context_sources or []),
            model_tier=event.model_policy,
            engine=event.engine or "",
            ingested_at=now,
        ),
    )

    if kind == "review":
        review = event.review_result
        assert review is not None
        record = record.model_copy(
            update={
                "findings": review.findings,
                "files_inspected": review.files_inspected,
                "blast_radius": review.blast_radius,
                "confidence": review.confidence,
                "review_result": review,
                "recommended_next_step": RecommendedNextStep(
                    command=_normalize_command(review.recommended_next_command, default="plan"),
                    rationale="Structured review recommended next command",
                    machine_readable=review.model_dump(mode="json"),
                ),
            }
        )
    else:
        plan = event.plan_result
        assert plan is not None
        record = record.model_copy(
            update={
                "blast_radius": plan.blast_radius,
                "confidence": plan.confidence,
                "uncertain_hypotheses": list(plan.assumptions),
                "unresolved_questions": list(plan.open_questions),
                "suspected_root_cause": plan.scope_summary or None,
                "plan_result": plan,
                "recommended_next_step": RecommendedNextStep(
                    command=_normalize_command(plan.recommended_next_command, default="fix"),
                    rationale="Structured plan recommended next command",
                    machine_readable=plan.model_dump(mode="json"),
                ),
            }
        )

    return record


def _command_kind_from_flow(flow: str) -> str | None:
    if flow == "code_review":
        return "review"
    if flow == "planner":
        return "plan"
    return None


def _model_risk_tags(event: AgentRunCompletedEvent, kind: str) -> list[str]:
    if kind == "review" and event.review_result is not None:
        return collect_risk_tags_from_review(event.review_result)
    if kind == "plan" and event.plan_result is not None:
        return collect_risk_tags_from_plan(event.plan_result)
    return list(event.risk_tags or [])


def _merge_risk_tag_sources(
    model_tags: list[str],
    gate_tags: list[RiskTagSource],
) -> list[RiskTagSource]:
    by_tag: dict[str, RiskTagSource] = {}
    for tag in model_tags:
        by_tag[tag] = RiskTagSource(tag=tag, source="model_output")
    for item in gate_tags:
        by_tag[item.tag] = item
    return sorted(by_tag.values(), key=lambda x: x.tag)


def _confidence_for(event: AgentRunCompletedEvent, kind: str) -> str:
    if kind == "review" and event.review_result is not None:
        return event.review_result.confidence
    if kind == "plan" and event.plan_result is not None:
        return event.plan_result.confidence
    return "medium"


def _risk_class_int(risk_class: str) -> int:
    mapping = {
        "read_only": 0,
        "read_only_with_repo_context": 1,
        "planning_only": 1,
        "write_patch": 2,
        "executes_untrusted_code": 3,
    }
    if risk_class.isdigit():
        return int(risk_class)
    return mapping.get(risk_class, 1)


def _normalize_command(raw: str, *, default: str) -> str:
    text = (raw or "").strip().lower().lstrip("/")
    if text.startswith("agent "):
        text = text[6:].strip()
    if text in ("review", "plan", "fix", "inspect", "explain", "human"):
        return text
    return default
