"""Dispatch verification state to CT104 rlm-root jobs."""

from __future__ import annotations

from typing import Any

from agent_control.config import Settings, get_settings
from agent_control.graph.context_pack import compile_context_pack
from agent_control.workflows.issue_task_backfill import maybe_backfill_command_intent
from agent_control.project_registry import (
    build_trigger_context,
    resolve_policy_source_pin,
    resolve_project,
    resolve_refs,
)
from agent_workers.executor.lifecycle import issue_ct103_nonce
from agent_shared.constants import FLOW_VERSIONS, INTENT_KIND_TO_FLOW, RiskClass
from agent_shared.models.intent import CommandIntent
from agent_shared.models.jobs import (
    JobLimits,
    JobSafety,
    RLMJob,
    ReplyPolicy,
    ReplyTarget,
    TriggerContext,
)
from agent_shared.models.state import VerificationState
from agent_shared.project_ids import (
    make_proposed_agent_branch,
    make_rlm_root_job_id,
    make_run_id,
    split_project,
)


def _safety_for_risk(risk: RiskClass, kind: str) -> JobSafety:
    write = risk in (RiskClass.WRITE_PATCH, RiskClass.EXECUTES_UNTRUSTED_CODE)
    tests = risk == RiskClass.EXECUTES_UNTRUSTED_CODE
    return JobSafety(
        activation_required=True,
        command_scope=kind,
        allow_repo_write=write,
        allow_test_execution=tests,
        allow_network=False,
        allow_push=False,
        allow_merge=False,
        sandbox_required=risk in (RiskClass.WRITE_PATCH, RiskClass.EXECUTES_UNTRUSTED_CODE),
        requires_manual_approval=write,
    )


def _limits_for_kind(kind: str) -> JobLimits:
    if kind in ("inspect", "explain"):
        return JobLimits(max_depth=0, max_child_agents=0, max_parallel_children=0, max_iterations=3, time_budget_seconds=300)
    if kind == "review":
        return JobLimits(max_depth=1, max_child_agents=2, max_parallel_children=1, max_iterations=6, time_budget_seconds=600)
    if kind == "plan":
        return JobLimits(max_depth=1, max_child_agents=2, max_parallel_children=1, max_iterations=6, time_budget_seconds=900)
    return JobLimits()


def build_rlm_job(
    state: VerificationState,
    trigger_event: dict[str, Any],
    settings: Settings | None = None,
) -> RLMJob | None:
    settings = settings or get_settings()
    intent = state.command_intent
    if not intent or not state.dispatch_recommended or not intent.kind:
        return None

    kind = intent.kind
    if kind not in INTENT_KIND_TO_FLOW:
        return None
    flow, agent, risk = INTENT_KIND_TO_FLOW[kind]
    if risk in (RiskClass.WRITE_PATCH, RiskClass.EXECUTES_UNTRUSTED_CODE):
        return None

    project = state.project
    owner, repo = split_project(project)
    cfg = resolve_project(project, settings=settings)
    refs = resolve_refs(project, trigger_event, settings=settings)
    pin = resolve_policy_source_pin(project, settings=settings)
    flow_meta = FLOW_VERSIONS.get(flow, FLOW_VERSIONS["inspect"])

    trigger_event_id = trigger_event.get("event_id", "unknown")
    run_id = make_run_id(trigger_event_id)
    job_id = make_rlm_root_job_id(trigger_event_id)

    body = (trigger_event.get("payload") or {}).get("comment", {}).get("body", "")
    if not body and intent.natural_language_task:
        body = f"/agent {kind} {intent.natural_language_task}"

    tc_raw = build_trigger_context(trigger_event, body, settings=settings)
    reply_target = None
    if tc_raw.get("reply_target"):
        reply_target = ReplyTarget(**tc_raw["reply_target"])
    trigger_context = TriggerContext(**{**tc_raw, "reply_target": reply_target})

    summaries = settings.agent_state_root / "projects" / owner / repo / "summaries"
    state_path = str(summaries / "verification_state.json")

    context_pack = None
    if kind in ("review", "plan"):
        context_pack = compile_context_pack(
            project,
            trigger_context,
            refs=refs,
            settings=settings,
            command_kind=kind,
        )

    intent = maybe_backfill_command_intent(
        intent,
        kind=kind,
        context_pack=context_pack,
        issue_number=trigger_context.issue_number,
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
        workload_ref=None,
        proposed_agent_branch=make_proposed_agent_branch(run_id),
        trigger_event_id=trigger_event_id,
        trigger_delivery_id=trigger_event.get("delivery_id"),
        trigger_type=trigger_event.get("type", ""),
        trigger_context=trigger_context,
        flow=flow_meta["flow_config_id"],
        agent=agent,
        risk_class=risk,
        command_intent=intent,
        reporting=ReplyPolicy(),
        limits=_limits_for_kind(kind),
        safety=_safety_for_risk(risk, kind),
        model_policy=settings.model_routing_policy,
        state_path=state_path,
        context_pack=context_pack,
        attestation_nonce=issue_ct103_nonce(),
    )


def maybe_dispatch_rlm_root(
    state: VerificationState,
    trigger_event: dict[str, Any],
    redis_url: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    from agent_control.gitea_comments import post_issue_comment
    from agent_control.invocation_ack import (
        format_invocation_started,
        format_invocation_terminal,
        identity_audit_from_session,
        invoker_fields_from_trigger,
    )
    from agent_control.queue import enqueue_rlm_root
    from agent_control.session import (
        TYPED_SESSION_COMMANDS,
        finalize_enqueue_failure,
        load_session_by_run,
    )
    from agent_control.session.prepare_dispatch import (
        PreflightFatalError,
        prepare_typed_rlm_dispatch,
    )
    from agent_shared.constants import QUEUE_RLM_ROOT

    settings = settings or get_settings()
    job = build_rlm_job(state, trigger_event, settings=settings)
    if job is None:
        return {"dispatched": False, "reason": "no_dispatch"}

    session = None
    kind = (job.command_intent.kind if job.command_intent else None) or ""
    invoker = invoker_fields_from_trigger(
        job.trigger_context,
        delivery_id=job.trigger_delivery_id,
    )
    issue_number = job.trigger_context.issue_number

    def _post_ack(body: str) -> None:
        if issue_number is None:
            return
        try:
            post_issue_comment(job.project, int(issue_number), body, settings=settings)
        except Exception:
            # Comment failure must not roll back enqueue / session state.
            pass

    if kind in TYPED_SESSION_COMMANDS:
        try:
            prepared = prepare_typed_rlm_dispatch(
                settings.agent_state_root,
                job,
                settings=settings,
            )
        except PreflightFatalError as exc:
            if issue_number is not None:
                _post_ack(
                    format_invocation_terminal(
                        outcome="failure",
                        command=kind,
                        run_id=job.run_id,
                        invoked_by=invoker["invoked_by"],
                        reason=str(exc),
                        reason_code="preflight_failed",
                        invoked_by_id=invoker["invoked_by_id"],
                        source_comment_id=invoker["source_comment_id"],
                        source_delivery_id=invoker["source_delivery_id"],
                        settings=settings,
                    )
                )
            return {
                "dispatched": False,
                "reason": "preflight_failed",
                "run_id": job.run_id,
                "error": str(exc),
            }
        job = prepared.job
        session = prepared.session

    enqueue_result = enqueue_rlm_root(redis_url, job.model_dump(mode="json"))
    if enqueue_result.outcome == "failed":
        if session is not None:
            finalize_enqueue_failure(
                settings.agent_state_root,
                session,
                run_id=job.run_id,
                reason=enqueue_result.error or "enqueue failed",
            )
        _post_ack(
            format_invocation_terminal(
                outcome="failure",
                command=kind or "command",
                run_id=job.run_id,
                invoked_by=invoker["invoked_by"],
                reason=enqueue_result.error or "enqueue failed",
                reason_code="enqueue_failed",
                session_id=session.session_id if session else None,
                invoked_by_id=invoker["invoked_by_id"],
                source_comment_id=invoker["source_comment_id"],
                source_delivery_id=invoker["source_delivery_id"],
                settings=settings,
            )
        )
        raise RuntimeError(enqueue_result.error or "enqueue failed")

    if enqueue_result.outcome == "deduplicated":
        existing = load_session_by_run(
            settings.agent_state_root, job.project, job.run_id
        )
        out: dict[str, Any] = {
            "dispatched": False,
            "reason": "deduplicated",
            "run_id": job.run_id,
            "existing_job_id": enqueue_result.existing_job_id,
        }
        sid = existing.session_id if existing else (session.session_id if session else None)
        if sid:
            out["session_id"] = sid
        return out

    result: dict[str, Any] = {
        "dispatched": True,
        "job_id": enqueue_result.job_id,
        "run_id": job.run_id,
        "flow": job.flow,
    }
    if session is not None:
        result["session_id"] = session.session_id
        if job.memory_preflight_digest:
            result["memory_preflight_digest"] = job.memory_preflight_digest
        if job.context_packet_digest:
            result["context_packet_digest"] = job.context_packet_digest
        audit = identity_audit_from_session(session, run_id=job.run_id, settings=settings)
        _post_ack(
            format_invocation_started(
                command=kind,
                run_id=job.run_id,
                invoked_by=audit.invoked_by,
                session_id=session.session_id,
                queue=QUEUE_RLM_ROOT,
                host="ct104",
                invoked_by_id=audit.invoked_by_id,
                source_comment_id=audit.source_comment_id,
                source_delivery_id=audit.source_delivery_id,
                settings=settings,
            )
        )
    else:
        _post_ack(
            format_invocation_started(
                command=kind or "command",
                run_id=job.run_id,
                invoked_by=invoker["invoked_by"],
                queue=QUEUE_RLM_ROOT,
                host="ct104",
                invoked_by_id=invoker["invoked_by_id"],
                source_comment_id=invoker["source_comment_id"],
                source_delivery_id=invoker["source_delivery_id"],
                settings=settings,
            )
        )
    return result


def dispatch(event: dict) -> dict:
    """CLI stub entry — build job without enqueue when called manually."""
    project = f"{event.get('owner')}/{event.get('repo')}"
    intent = CommandIntent(activated=True, activation="/agent", kind=event.get("event"), natural_language_task="manual", confidence=1.0)
    state = VerificationState(project=project, command_intent=intent, dispatch_recommended=True, dispatch_kind=event.get("event"))
    job = build_rlm_job(state, {"event_id": "manual", "type": "gitea.issue_comment", "project": project, "payload": {}})
    if job is None:
        return {"status": "no_dispatch"}
    return {"status": "ok", "job": job.model_dump(mode="json")}
