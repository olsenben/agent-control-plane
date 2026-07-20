"""Build and enqueue Risk 2 fix RLM jobs (Slice 6B + 6D)."""

from __future__ import annotations

import os
from typing import Any

from agent_control.approval.events import append_approval_reserved, append_fix_enqueued
from agent_control.approval.plan_lookup import PlanRunRecord
from agent_control.approval.service import reserve_approval_for_fix
from agent_control.config import Settings, get_settings
from agent_control.graph.context_pack import compile_context_pack
from agent_control.project_registry import (
    build_trigger_context,
    resolve_policy_source_pin,
    resolve_project,
    resolve_refs,
)
from agent_control.queue import enqueue_rlm_root
from agent_shared.approval_ids import derive_approval_target_id, derive_plan_alias
from agent_shared.constants import FLOW_VERSIONS, RiskClass
from agent_shared.hash_utils import hash_blast_radius
from agent_shared.models.approval import (
    ApprovalReservedEvent,
    FixAuthorizationBinding,
    FixEnqueuedEvent,
    FixPlanStepBinding,
    WorkItemApproval,
)
from agent_shared.models.intent import CommandIntent
from agent_shared.models.jobs import JobLimits, JobSafety, RLMJob, ReplyPolicy
from agent_shared.project_ids import (
    make_proposed_agent_branch,
    make_rlm_root_job_id,
    make_run_id,
    split_project,
)
from agent_workers.executor.lifecycle import issue_ct103_nonce


def fix_remote_publish_enabled(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    env_val = os.environ.get("FIX_REMOTE_PUBLISH_ENABLED", "").lower()
    if env_val in ("1", "true", "yes"):
        return True
    return getattr(settings, "fix_remote_publish_enabled", False)


def _limits_for_fix() -> JobLimits:
    return JobLimits(
        max_depth=0,
        max_child_agents=0,
        max_parallel_children=0,
        max_iterations=4,
        time_budget_seconds=900,
    )


def _safety_for_fix(settings: Settings | None = None) -> JobSafety:
    publish = fix_remote_publish_enabled(settings)
    return JobSafety(
        activation_required=True,
        command_scope="fix",
        allow_repo_write=True,
        allow_test_execution=False,
        allow_network=publish,
        allow_push=publish,
        allow_merge=False,
        sandbox_required=True,
        requires_manual_approval=False,
    )


def build_fix_authorization_binding(
    approval: WorkItemApproval,
    plan_record: PlanRunRecord,
) -> FixAuthorizationBinding:
    plan = plan_record.plan_result
    return FixAuthorizationBinding(
        approval_id=approval.approval_id,
        approval_target_id=approval.approval_target_id,
        plan_run_id=plan_record.run_id,
        plan_hash=approval.plan_hash,
        blast_radius_hash=approval.blast_radius_hash,
        allowed_files=list(approval.allowed_files),
        plan_summary=plan.scope_summary,
        plan_steps=[
            FixPlanStepBinding(id=step.id, summary=step.summary, files=list(step.files))
            for step in plan.steps
        ],
        ci_hints=list(plan.ci_hints),
        approved_base_sha=approval.approved_base_sha,
        approved_base_ref=approval.approved_base_ref,
    )


def build_fix_rlm_job(
    *,
    trigger_event: dict[str, Any],
    evaluation_approval: WorkItemApproval,
    plan_record: PlanRunRecord,
    fix_run_id: str | None = None,
    settings: Settings | None = None,
) -> RLMJob:
    settings = settings or get_settings()
    project = plan_record.project
    owner, repo = split_project(project)
    cfg = resolve_project(project, settings=settings)
    refs = resolve_refs(project, trigger_event, settings=settings)
    pin = resolve_policy_source_pin(project, settings=settings)
    flow_meta = FLOW_VERSIONS["developer_flow"]

    trigger_event_id = trigger_event.get("event_id", "unknown")
    run_id = fix_run_id or make_run_id(trigger_event_id)
    job_id = make_rlm_root_job_id(f"{trigger_event_id}-fix")

    body = (trigger_event.get("payload") or {}).get("comment", {}).get("body", "")
    target = evaluation_approval.approval_target_id
    tc_raw = build_trigger_context(trigger_event, body, settings=settings)

    from agent_shared.models.jobs import ReplyTarget, TriggerContext

    reply_target = None
    if tc_raw.get("reply_target"):
        reply_target = ReplyTarget(**tc_raw["reply_target"])
    trigger_context = TriggerContext(**{**tc_raw, "reply_target": reply_target})

    binding = build_fix_authorization_binding(evaluation_approval, plan_record)
    context_pack = compile_context_pack(
        project,
        trigger_context,
        refs=refs,
        settings=settings,
        command_kind="fix",
        changed_files=binding.allowed_files,
    )
    plan_br = plan_record.plan_result.blast_radius
    if hash_blast_radius(context_pack.blast_radius) != binding.blast_radius_hash:
        if hash_blast_radius(plan_br) == binding.blast_radius_hash:
            context_pack = context_pack.model_copy(update={"blast_radius": plan_br})

    summaries = settings.agent_state_root / "projects" / owner / repo / "summaries"
    state_path = str(summaries / "verification_state.json")

    intent = CommandIntent(
        activated=True,
        activation="/agent",
        kind="fix",
        natural_language_task=target,
        approval_target=target,
        work_item_id=target,
        confidence=1.0,
    )

    return RLMJob(
        run_id=run_id,
        job_id=job_id,
        workflow_id=run_id,
        session_id=run_id,
        workflow_definition=flow_meta["workflow_definition"],
        flow_config_id=flow_meta["flow_config_id"],
        flow_version=flow_meta["flow_version"],
        flow_config_schema_version=flow_meta["flow_config_schema_version"],
        project=project,
        owner=owner,
        repo=repo,
        repo_url=cfg.repo_url,
        primary_branch=cfg.default_branch,
        **pin.as_job_fields(),
        base_ref=refs.base_ref,
        target_sha=refs.target_sha,
        task_ref=refs.task_ref,
        proposed_agent_branch=make_proposed_agent_branch(run_id),
        trigger_event_id=trigger_event_id,
        trigger_delivery_id=trigger_event.get("delivery_id"),
        trigger_type=trigger_event.get("type", ""),
        trigger_context=trigger_context,
        flow=flow_meta["flow_config_id"],
        agent="developer",
        risk_class=RiskClass.WRITE_PATCH,
        command_intent=intent,
        reporting=ReplyPolicy(),
        limits=_limits_for_fix(),
        safety=_safety_for_fix(settings),
        model_policy=settings.model_routing_policy,
        state_path=state_path,
        context_pack=context_pack,
        fix_authorization=binding,
        attestation_nonce=issue_ct103_nonce(),
    )


def enqueue_fix_after_authorization(
    state_root,
    *,
    trigger_event: dict[str, Any],
    approval: WorkItemApproval,
    plan_record: PlanRunRecord,
    comment_id: int | None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Build fix job, enqueue to CT104, reserve approval (consume on PR open via ingest)."""
    from agent_control.session import (
        begin_typed_session,
        bind_session_to_job,
        finalize_enqueue_failure,
    )

    settings = settings or get_settings()
    job = build_fix_rlm_job(
        trigger_event=trigger_event,
        evaluation_approval=approval,
        plan_record=plan_record,
        settings=settings,
    )

    session = begin_typed_session(
        state_root,
        project=job.project,
        command_kind="fix",
        run_id=job.run_id,
        head_sha=job.target_sha or approval.approved_base_sha or "",
        trigger_context=job.trigger_context,
        policy_source_sha=job.policy_source_sha or "",
        # Sparse trigger events (tests / CLI) still bind to the approval issue.
        subject_kind="issue",
        subject_number=approval.issue_id,
        invoked_by=approval.approved_by_login,
    )
    job = bind_session_to_job(job, session)

    try:
        job_id = enqueue_rlm_root(settings.redis_url, job.model_dump(mode="json"))
    except Exception as exc:
        finalize_enqueue_failure(
            state_root,
            session,
            run_id=job.run_id,
            reason=str(exc),
        )
        raise

    if job_id is None:
        return {
            "enqueued": False,
            "reason": "deduped_or_failed",
            "run_id": job.run_id,
            "session_id": session.session_id,
        }

    enqueued_body = FixEnqueuedEvent(
        fix_run_id=job.run_id,
        job_id=job_id,
        approval_id=approval.approval_id,
        approval_target_id=approval.approval_target_id,
        plan_run_id=plan_record.run_id,
        project=approval.project,
        issue_id=approval.issue_id,
        approval_reserved=True,
    )
    enq_path, enq_created = append_fix_enqueued(
        state_root,
        body=enqueued_body,
        comment_id=comment_id,
    )

    reserved = reserve_approval_for_fix(
        state_root,
        approval,
        fix_run_id=job.run_id,
    )

    reserved_body = ApprovalReservedEvent(
        approval_id=reserved.approval_id,
        approval_target_id=reserved.approval_target_id,
        plan_run_id=plan_record.run_id,
        project=reserved.project,
        issue_id=reserved.issue_id,
        reserved_by_fix_run_id=job.run_id,
    )
    append_approval_reserved(
        state_root,
        body=reserved_body,
        comment_id=comment_id,
    )

    return {
        "enqueued": True,
        "run_id": job.run_id,
        "session_id": session.session_id,
        "job_id": job_id,
        "fix_enqueued_created": enq_created,
        "approval_reserved": True,
        "approval_target_id": approval.approval_target_id,
        "plan_alias": derive_plan_alias(plan_record.run_id),
        "approval_target": derive_approval_target_id(
            issue_id=approval.issue_id,
            plan_run_id=plan_record.run_id,
        ),
    }
