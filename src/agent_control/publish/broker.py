"""CT103 publish broker orchestration (fix + repair)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from agent_control.approval.service import (
    claim_approval_for_publish,
    consume_approval_on_pr_open,
    release_approval_claim,
)
from agent_control.approval.storage import load_approval
from agent_control.ci.pending import register_pending_ci
from agent_control.config import Settings, get_settings
from agent_control.gitea_client import GiteaClient
from agent_control.gitea_comments import post_issue_comment
from agent_control.publish.remote import (
    RemoteMutationError,
    build_commit_message,
    build_pr_body,
    open_or_find_pr,
    push_commit,
    push_repair_fast_forward,
)
from agent_control.publish.state import (
    cas_transition,
    load_publish_record,
)
from agent_control.publish.validate import ValidationError, validate_and_commit
from agent_control.session.reasons import classify_broker_reject
from agent_shared.bundles.inbox import BundleError, copy_bundle_to_snapshot, load_ready_bundle
from agent_shared.models.approval import FixAuthorizationBinding
from agent_shared.models.bundle import AuthoritativePublishResult
from agent_shared.models.fix import FixResult
from agent_shared.project_ids import split_project


def _terminalize_broker_reject(
    state_root: Path,
    *,
    project: str | None,
    run_id: str,
    broker_reason: str,
    detail: list[str] | str | None = None,
) -> None:
    if not project:
        return
    from agent_control.session import handle_publish_session_terminal

    terminal, reason_code = classify_broker_reject(
        broker_reason=broker_reason,
        detail=detail if isinstance(detail, list) else ([str(detail)] if detail else []),
    )
    domain = detail if isinstance(detail, list) else ([str(detail)] if detail else [])
    handle_publish_session_terminal(
        state_root,
        project=project,
        run_id=run_id,
        terminal=terminal,
        reason_code=reason_code,
        domain_reasons=domain,
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_auth_result(state_root: Path, result: AuthoritativePublishResult) -> Path:
    path = (
        state_root
        / "publish-results"
        / result.run_id
        / result.bundle_id
        / "remote_publish_result.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return path


def _load_binding_from_approval(approval) -> FixAuthorizationBinding:
    return FixAuthorizationBinding(
        approval_id=approval.approval_id,
        approval_target_id=approval.approval_target_id,
        plan_run_id=approval.plan_run_id,
        plan_hash=approval.plan_hash,
        blast_radius_hash=approval.blast_radius_hash,
        allowed_files=list(approval.allowed_files),
        approved_base_sha=approval.approved_base_sha,
        approved_base_ref=approval.approved_base_ref,
    )


def _pdp_reject_payload(pdp) -> dict:
    from agent_control.transaction.admission import ESCALATE

    if pdp.decision == ESCALATE:
        payload = {
            "ok": False,
            "reason": "admission_escalate",
            "decision": pdp.decision,
            "detail": list(pdp.reasons),
        }
        if pdp.escalation is not None:
            payload["escalation_id"] = pdp.escalation.escalation_id
            payload["admission_escalation"] = pdp.escalation.model_dump(mode="json")
        return payload
    return {
        "ok": False,
        "reason": "admission_reject",
        "decision": pdp.decision,
        "detail": list(pdp.reasons),
        "decision_digest": pdp.admission.decision_digest,
    }


def _run_broker_pdp(
    *,
    state_root: Path,
    project: str,
    run_id: str,
    attempt_id: str,
    bundle_id: str,
    bundle_root: Path,
    manifest,
    authorized_files: list[str],
    source_sha: str,
    agent_branch: str,
    invoked_by: str,
    kind: str,
    record,
) -> tuple[object | None, dict | None]:
    """Frozen C PDP. Returns (pdp, None) on AUTO_ADMIT else (None, reject dict)."""
    from agent_control.publish.pdp import run_publish_pdp
    from agent_control.transaction.admission import AUTO_ADMIT, ESCALATE
    from agent_control.transaction.barriers import DurableBarrierError

    try:
        pdp = run_publish_pdp(
            state_root=state_root,
            project=project,
            run_id=run_id,
            bundle_id=bundle_id,
            bundle_root=bundle_root,
            manifest=manifest,
            authorized_files=authorized_files,
            source_sha=source_sha,
            agent_branch=agent_branch,
            invoked_by=invoked_by,
        )
    except DurableBarrierError as exc:
        cas_transition(
            state_root,
            run_id=run_id,
            kind=kind,
            attempt_id=attempt_id,
            bundle_id=bundle_id,
            from_state="validating",
            to_state="rejected",
            messages=[exc.code],
        )
        _terminalize_broker_reject(
            state_root,
            project=record.project if record else project,
            run_id=run_id,
            broker_reason=exc.code.lower(),
            detail=[exc.code],
        )
        return None, {"ok": False, "reason": exc.code, "published": False}
    if pdp.decision == AUTO_ADMIT:
        return pdp, None
    cas_transition(
        state_root,
        run_id=run_id,
        kind=kind,
        attempt_id=attempt_id,
        bundle_id=bundle_id,
        from_state="validating",
        to_state="rejected",
        messages=[pdp.decision, *list(pdp.reasons)],
    )
    broker_reason = (
        "admission_escalate" if pdp.decision == ESCALATE else "admission_reject"
    )
    detail = (
        ["human_approval_required", *list(pdp.reasons)]
        if pdp.decision == ESCALATE
        else list(pdp.reasons)
    )
    _terminalize_broker_reject(
        state_root,
        project=record.project if record else project,
        run_id=run_id,
        broker_reason=broker_reason,
        detail=detail,
    )
    return None, _pdp_reject_payload(pdp)


def _complete_broker_capability(pdp: object) -> None:
    from agent_control.publish.pdp import witness_and_complete_consume

    if getattr(pdp, "capability", None) is None:
        return
    witness_and_complete_consume(pdp)  # type: ignore[arg-type]


def broker_publish_fix(
    *,
    state_root: Path,
    run_id: str,
    attempt_id: str,
    bundle_id: str,
    settings: Settings | None = None,
) -> dict:
    """Validate snapshot, claim approval, CI intent, push, open PR, consume."""
    settings = settings or get_settings()
    record = load_publish_record(state_root, run_id, bundle_id)
    if record and record.publish_state == "succeeded":
        return {"ok": True, "idempotent": True, "publish_state": "succeeded"}

    cas_transition(
        state_root,
        run_id=run_id,
        kind="fix",
        attempt_id=attempt_id,
        bundle_id=bundle_id,
        from_state="queued",
        to_state="validating",
    )

    try:
        manifest, bundle_root = load_ready_bundle(
            state_root,
            run_id=run_id,
            kind="fix",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
        )
        from agent_control.publish.eligibility import evaluate_publish_eligible

        eligibility = evaluate_publish_eligible(
            bundle_dir=bundle_root,
            manifest=manifest,
            require_attestations=True,
        )
        if not eligibility.eligible:
            cas_transition(
                state_root,
                run_id=run_id,
                kind="fix",
                attempt_id=attempt_id,
                bundle_id=bundle_id,
                from_state="validating",
                to_state="rejected",
                messages=eligibility.reason_codes + eligibility.messages,
            )
            _terminalize_broker_reject(
                state_root,
                project=record.project if record else None,
                run_id=run_id,
                broker_reason="attestation_gate",
                detail=eligibility.reason_codes,
            )
            return {
                "ok": False,
                "reason": "attestation_gate",
                "detail": eligibility.reason_codes,
            }
        snapshot = copy_bundle_to_snapshot(
            state_root,
            run_id=run_id,
            kind="fix",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
        )
    except BundleError as exc:
        cas_transition(
            state_root,
            run_id=run_id,
            kind="fix",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
            from_state="validating",
            to_state="rejected",
            messages=[str(exc)],
        )
        _terminalize_broker_reject(
            state_root,
            project=record.project if record else None,
            run_id=run_id,
            broker_reason="bundle_invalid",
            detail=[str(exc)],
        )
        return {"ok": False, "reason": "bundle_invalid", "detail": str(exc)}

    project = record.project if record else None
    approval_target_id = record.approval_target_id if record else None
    if not project or not approval_target_id:
        cas_transition(
            state_root,
            run_id=run_id,
            kind="fix",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
            from_state="validating",
            to_state="failed_terminal",
            messages=["missing project/approval on publish record"],
        )
        _terminalize_broker_reject(
            state_root,
            project=project,
            run_id=run_id,
            broker_reason="missing_binding",
        )
        return {"ok": False, "reason": "missing_binding"}

    approval = load_approval(state_root, project, approval_target_id)
    if approval is None:
        cas_transition(
            state_root,
            run_id=run_id,
            kind="fix",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
            from_state="validating",
            to_state="failed_terminal",
            messages=["approval not found"],
        )
        _terminalize_broker_reject(
            state_root,
            project=project,
            run_id=run_id,
            broker_reason="approval_missing",
        )
        return {"ok": False, "reason": "approval_missing"}

    if approval.status in ("rejected", "expired", "consumed"):
        cas_transition(
            state_root,
            run_id=run_id,
            kind="fix",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
            from_state="validating",
            to_state="failed_terminal",
            messages=[f"approval status {approval.status}"],
        )
        _terminalize_broker_reject(
            state_root,
            project=project,
            run_id=run_id,
            broker_reason="approval_unavailable",
            detail=[f"approval status {approval.status}"],
        )
        return {"ok": False, "reason": "approval_unavailable"}

    trusted_sha = approval.approved_base_sha
    if not trusted_sha:
        cas_transition(
            state_root,
            run_id=run_id,
            kind="fix",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
            from_state="validating",
            to_state="failed_terminal",
            messages=["no approved_base_sha"],
        )
        _terminalize_broker_reject(
            state_root,
            project=project,
            run_id=run_id,
            broker_reason="no_trusted_sha",
        )
        return {"ok": False, "reason": "no_trusted_sha"}

    binding = _load_binding_from_approval(approval)
    # Resolve repo URL from CT103 config + project — never from worker
    owner, repo = split_project(project)
    repo_url = f"{settings.gitea_base_url.rstrip('/')}/{owner}/{repo}.git"
    agent_branch = f"agent/{run_id}"
    base_ref = approval.approved_base_ref or "main"

    from agent_control.authorization import (
        append_authorization_decision,
        recheck_publish_authorization,
    )
    from agent_control.session.storage import load_session_by_run

    session = load_session_by_run(state_root, project, run_id)
    invoker_login = (
        (session.invoked_by if session else None)
        or approval.approved_by_login
        or "unknown"
    )
    session_id = session.session_id if session else None
    approved_by = (session.approved_by if session else None) or approval.approved_by_login

    approval_valid = True
    approval_reason = ""
    try:
        client = GiteaClient(settings)
        remote_sha = client.get_branch_sha(owner, repo, base_ref)
        if remote_sha and trusted_sha and remote_sha != trusted_sha:
            approval_valid = False
            approval_reason = (
                f"source_sha_drift approved={trusted_sha[:12]} remote={remote_sha[:12]}"
            )
    except Exception as exc:
        # Fail closed on publish when we cannot confirm base SHA.
        approval_valid = False
        approval_reason = f"source_sha_recheck_failed: {exc}"

    auth = recheck_publish_authorization(
        project=project,
        invoker_login=invoker_login,
        approver_login=approved_by,
        source_sha=trusted_sha or "",
        policy_source_sha=(session.policy_source_sha if session else "") or "",
        approval_valid=approval_valid,
        approval_reason=approval_reason,
        run_id=run_id,
        session_id=session_id,
        settings=settings,
    )
    append_authorization_decision(state_root, auth)
    if auth.decision == "deny":
        cas_transition(
            state_root,
            run_id=run_id,
            kind="fix",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
            from_state="validating",
            to_state="failed_terminal",
            messages=[f"authorization_denied: {auth.approval_scope.reason or auth.decision}"],
        )
        _terminalize_broker_reject(
            state_root,
            project=project,
            run_id=run_id,
            broker_reason="authorization_denied",
            detail=[auth.approval_scope.reason or auth.acting_identity_check.reason],
        )
        return {
            "ok": False,
            "reason": "authorization_denied",
            "authorization": auth.model_dump(mode="json"),
        }

    pdp, pdp_reject = _run_broker_pdp(
        state_root=state_root,
        project=project,
        run_id=run_id,
        attempt_id=attempt_id,
        bundle_id=bundle_id,
        bundle_root=bundle_root,
        manifest=manifest,
        authorized_files=list(binding.allowed_files),
        source_sha=trusted_sha,
        agent_branch=agent_branch,
        invoked_by=invoker_login,
        kind="fix",
        record=record,
    )
    if pdp_reject is not None:
        return pdp_reject

    from agent_control.transaction.barriers import (
        DurableBarrierError,
        PHASE_PUBLISH,
        check_durable_effect_allowed,
    )

    try:
        check_durable_effect_allowed(state_root, run_id=run_id, phase=PHASE_PUBLISH)
    except DurableBarrierError as exc:
        cas_transition(
            state_root,
            run_id=run_id,
            kind="fix",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
            from_state="validating",
            to_state="rejected",
            messages=[exc.code],
        )
        _terminalize_broker_reject(
            state_root,
            project=project,
            run_id=run_id,
            broker_reason=exc.code.lower(),
            detail=[exc.code],
        )
        return {"ok": False, "reason": exc.code, "published": False}

    commit_msg = build_commit_message(
        run_id=run_id,
        binding=binding,
        approved_base_sha=trusted_sha,
        invoked_by=invoker_login,
        session_id=session_id,
        approved_by=approved_by,
    )

    try:
        validated = validate_and_commit(
            settings=settings,
            snapshot_dir=snapshot,
            manifest=manifest,
            binding=binding,
            repo_url=repo_url,
            trusted_base_sha=trusted_sha,
            commit_message=commit_msg,
        )
    except ValidationError as exc:
        cas_transition(
            state_root,
            run_id=run_id,
            kind="fix",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
            from_state="validating",
            to_state="rejected",
            messages=[f"{exc.reason}: {exc}"],
        )
        _terminalize_broker_reject(
            state_root,
            project=project,
            run_id=run_id,
            broker_reason=exc.reason,
            detail=[str(exc)],
        )
        return {"ok": False, "reason": exc.reason, "detail": str(exc)}

    from agent_control.publish.pdp import witness_and_consume
    from agent_control.transaction.capability import CAPABILITY_ALREADY_CONSUMED

    consume = witness_and_consume(
        pdp,
        current_base_sha=trusted_sha,
        patch_digest=validated.patch_sha256,
        repo=project,
        target_ref=agent_branch,
        policy_digest=pdp.policy.policy_digest,
    )
    if not consume.get("allowed"):
        status = str(consume.get("status") or "STATE_WITNESS")
        cas_transition(
            state_root,
            run_id=run_id,
            kind="fix",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
            from_state="validating",
            to_state="rejected",
            messages=[status, *list(consume.get("reasons") or [])],
        )
        _terminalize_broker_reject(
            state_root,
            project=project,
            run_id=run_id,
            broker_reason=(
                "capability_consume_failed"
                if status == CAPABILITY_ALREADY_CONSUMED
                else "state_witness_failed"
            ),
            detail=list(consume.get("reasons") or [status]),
        )
        return {
            "ok": False,
            "reason": status,
            "detail": consume.get("reasons"),
            "published": False,
        }

    job_key = f"{run_id}:{bundle_id}"
    claimed = claim_approval_for_publish(
        state_root,
        approval,
        publish_job_id=job_key,
    )
    if claimed is None:
        cas_transition(
            state_root,
            run_id=run_id,
            kind="fix",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
            from_state="validating",
            to_state="failed_retryable",
            messages=["approval claim failed"],
        )
        _terminalize_broker_reject(
            state_root,
            project=project,
            run_id=run_id,
            broker_reason="claim_failed",
        )
        return {"ok": False, "reason": "claim_failed"}

    from agent_control.publish.state import load_publish_intent
    from agent_control.transaction.ledger import record_publish_requested

    existing_intent = load_publish_intent(state_root, project, validated.commit_sha)
    cap_id = pdp.capability.capability_id if getattr(pdp, "capability", None) else None
    record_publish_requested(
        state_root,
        project=project,
        transaction_id=str(getattr(pdp, "transaction_id", None) or run_id),
        capability_id=cap_id,
        patch_digest=str(getattr(pdp, "patch_digest", None) or validated.patch_sha256),
        repo=project,
        source_sha=trusted_sha,
        target_branch=agent_branch,
        expected_commit_sha=validated.commit_sha,
        run_id=run_id,
        bundle_id=bundle_id,
        kind="fix",
        publish_effect_id=existing_intent.publish_effect_id if existing_intent else None,
    )

    from agent_control.transaction.failpoints import FailpointAbort, hit as hit_failpoint

    hit_failpoint("after_intent_before_push", run_id=run_id, state_root=state_root)

    # Pending-CI intent before push (PR number may be filled later)
    register_pending_ci(
        state_root,
        fix_run_id=run_id,
        repository=project,
        expected_head_commit_sha=validated.commit_sha,
        opened_pr_number=None,
        issue_id=approval.issue_id,
        agent_branch=agent_branch,
    )

    cas_transition(
        state_root,
        run_id=run_id,
        kind="fix",
        attempt_id=attempt_id,
        bundle_id=bundle_id,
        from_state="validating",
        to_state="remote_pending",
        expected_commit_sha=validated.commit_sha,
        trusted_base_sha=trusted_sha,
        patch_sha256=validated.patch_sha256,
        result_tree_sha=validated.result_tree_sha,
        agent_branch=agent_branch,
    )

    client = GiteaClient(settings)
    try:
        # Verify remote base unchanged
        tip = client.get_branch_sha(owner, repo, base_ref)
        if tip != trusted_sha:
            release_approval_claim(state_root, claimed)
            cas_transition(
                state_root,
                run_id=run_id,
                kind="fix",
                attempt_id=attempt_id,
                bundle_id=bundle_id,
                from_state="remote_pending",
                to_state="failed_terminal",
                messages=["remote base advanced"],
            )
            _terminalize_broker_reject(
                state_root,
                project=project,
                run_id=run_id,
                broker_reason="stale_base",
            )
            return {"ok": False, "reason": "stale_base"}
    except RemoteMutationError as exc:
        release_approval_claim(state_root, claimed)
        cas_transition(
            state_root,
            run_id=run_id,
            kind="fix",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
            from_state="remote_pending",
            to_state="failed_retryable" if not exc.stale else "failed_terminal",
            messages=[str(exc)],
        )
        _terminalize_broker_reject(
            state_root,
            project=project,
            run_id=run_id,
            broker_reason="stale_base" if exc.stale else (exc.stage or "push_failed"),
            detail=[str(exc)],
        )
        return {"ok": False, "reason": exc.stage, "detail": str(exc), "stale": exc.stale}
    except FailpointAbort:
        raise
    except Exception as exc:
        from agent_control.transaction.retry import classify_exception as _classify

        classification = _classify(exc, request_sent=False)
        release_approval_claim(state_root, claimed)
        cas_transition(
            state_root,
            run_id=run_id,
            kind="fix",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
            from_state="remote_pending",
            to_state="failed_terminal" if classification.terminal else "failed_retryable",
            messages=[str(exc), classification.retry_class],
        )
        _terminalize_broker_reject(
            state_root,
            project=project,
            run_id=run_id,
            broker_reason="push_failed",
            detail=[str(exc)],
        )
        return {
            "ok": False,
            "reason": classification.retry_class,
            "detail": str(exc),
            "retry_class": classification.retry_class,
        }

    push_applied = False
    try:
        push_commit(
            workspace=validated.workspace,
            commit_sha=validated.commit_sha,
            agent_branch=agent_branch,
            base_ref=base_ref,
            repo_url=repo_url,
            settings=settings,
        )
        push_applied = True
    except RemoteMutationError as exc:
        release_approval_claim(state_root, claimed)
        cas_transition(
            state_root,
            run_id=run_id,
            kind="fix",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
            from_state="remote_pending",
            to_state="failed_retryable" if not exc.stale else "failed_terminal",
            messages=[str(exc)],
        )
        _terminalize_broker_reject(
            state_root,
            project=project,
            run_id=run_id,
            broker_reason="stale_base" if exc.stale else (exc.stage or "push_failed"),
            detail=[str(exc)],
        )
        return {"ok": False, "reason": exc.stage, "detail": str(exc), "stale": exc.stale}
    except FailpointAbort:
        raise
    except Exception as exc:
        from agent_control.transaction.ledger import append_transaction_control_event
        from agent_control.transaction.reconcile import (
            ExpectedPublishEffect,
            inspect_expected_effect,
            observe_from_client,
        )
        from agent_control.transaction.retry import (
            PERMANENT,
            classify_exception as _classify_push,
            exhaustion_event_payload,
            record_retry_attempt,
        )
        from agent_shared.models.transaction.ledger import TransactionControlEvent

        classification = _classify_push(exc, request_sent=True)
        if classification.requires_reconcile:
            expected = ExpectedPublishEffect(
                repo=project,
                branch=agent_branch,
                commit_sha=validated.commit_sha,
                transaction_id=str(getattr(pdp, "transaction_id", None) or run_id),
                run_id=run_id,
                bundle_id=bundle_id,
            )
            observed = observe_from_client(client, expected)
            decision = inspect_expected_effect(expected, observed)
            if decision.already_applied:
                push_applied = True
                if decision.matched_pr is not None:
                    _complete_broker_capability(pdp)
            else:
                budget = record_retry_attempt(state_root, run_id=run_id, scope="gitea_publish")
                terminal = bool(budget.get("exhausted")) or decision.retry_class == PERMANENT
                if budget.get("exhausted"):
                    exhausted = exhaustion_event_payload(
                        budget,
                        transaction_id=str(getattr(pdp, "transaction_id", None) or run_id),
                    )
                    append_transaction_control_event(
                        state_root,
                        TransactionControlEvent(
                            event_id=str(exhausted["event_id"]),
                            transaction_id=str(exhausted["transaction_id"]),
                            event_type="RETRY_EXHAUSTED",
                            component="publish_broker",
                            timestamp=str(exhausted["timestamp"]),
                            payload_digest=str(exhausted["payload_digest"]),
                            payload=exhausted,
                            repository=project,
                            run_id=run_id,
                        ),
                        project=project,
                    )
                release_approval_claim(state_root, claimed)
                cas_transition(
                    state_root,
                    run_id=run_id,
                    kind="fix",
                    attempt_id=attempt_id,
                    bundle_id=bundle_id,
                    from_state="remote_pending",
                    to_state="failed_terminal" if terminal else "failed_retryable",
                    messages=[str(exc), classification.retry_class, decision.reason],
                )
                if terminal:
                    _terminalize_broker_reject(
                        state_root,
                        project=project,
                        run_id=run_id,
                        broker_reason="push_failed",
                        detail=[str(exc), str(budget.get("exhaustion_code") or classification.retry_class)],
                    )
                return {
                    "ok": False,
                    "reason": classification.retry_class,
                    "retry_class": classification.retry_class,
                    "next_action": decision.next_action,
                    "reconcile_status": decision.status,
                    "detail": str(exc),
                }
        else:
            release_approval_claim(state_root, claimed)
            cas_transition(
                state_root,
                run_id=run_id,
                kind="fix",
                attempt_id=attempt_id,
                bundle_id=bundle_id,
                from_state="remote_pending",
                to_state="failed_terminal" if classification.terminal else "failed_retryable",
                messages=[str(exc), classification.retry_class],
            )
            _terminalize_broker_reject(
                state_root,
                project=project,
                run_id=run_id,
                broker_reason="push_failed",
                detail=[str(exc)],
            )
            return {
                "ok": False,
                "reason": classification.retry_class if classification.terminal else "push_failed",
                "detail": str(exc),
                "retry_class": classification.retry_class,
            }

    if not push_applied:
        return {"ok": False, "reason": "push_failed"}

    hit_failpoint("after_push_before_ack", run_id=run_id, state_root=state_root)

    # Load fix_result from snapshot for PR body if present
    fix_result = FixResult(files_changed=list(binding.allowed_files))
    result_file = snapshot / "fix_result.json"
    if result_file.is_file():
        try:
            fix_result = FixResult.model_validate(json.loads(result_file.read_text(encoding="utf-8")))
        except Exception:
            pass

    pr_body = build_pr_body(
        run_id=run_id,
        issue_number=approval.issue_id,
        binding=binding,
        fix_result=fix_result,
        approved_base_sha=trusted_sha,
        ci_hints=list(binding.ci_hints) if hasattr(binding, "ci_hints") else None,
    )
    # Idempotency marker
    pr_body = pr_body + f"\n\n<!-- agent-run-id:{run_id} bundle-id:{bundle_id} -->\n"
    title = f"agent(fix): {binding.approval_target_id}"

    try:
        pr_number, pr_url, _reused = open_or_find_pr(
            client=client,
            owner=owner,
            repo=repo,
            agent_branch=agent_branch,
            base_ref=base_ref,
            title=title,
            body=pr_body,
        )
    except FailpointAbort:
        raise
    except RemoteMutationError as exc:
        # Push succeeded — partial recovery path
        cas_transition(
            state_root,
            run_id=run_id,
            kind="fix",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
            from_state="remote_pending",
            to_state="failed_retryable",
            commit_sha=validated.commit_sha,
            messages=[f"pr_open: {exc}"],
        )
        return {
            "ok": False,
            "reason": "pr_open",
            "commit_sha": validated.commit_sha,
            "detail": str(exc),
        }

    hit_failpoint("after_pr_before_ack", run_id=run_id, state_root=state_root)

    # Update pending CI with PR number
    register_pending_ci(
        state_root,
        fix_run_id=run_id,
        repository=project,
        expected_head_commit_sha=validated.commit_sha,
        opened_pr_number=pr_number,
        issue_id=approval.issue_id,
        agent_branch=agent_branch,
    )

    hit_failpoint("after_ci_request_before_reducer", run_id=run_id, state_root=state_root)
    _complete_broker_capability(pdp)

    consume_approval_on_pr_open(
        state_root,
        claimed,
        fix_run_id=run_id,
        consumed_event_id=f"publish-{bundle_id}",
    )

    auth = AuthoritativePublishResult(
        run_id=run_id,
        bundle_id=bundle_id,
        attempt_id=attempt_id,
        kind="fix",
        trusted_base_sha=trusted_sha,
        patch_sha256=validated.patch_sha256,
        result_tree_sha=validated.result_tree_sha,
        commit_sha=validated.commit_sha,
        remote_branch=agent_branch,
        pr_number=pr_number,
        pr_url=pr_url,
        approval_binding_id=binding.approval_id,
        published_at=_now(),
        publish_state="succeeded",
    )
    _write_auth_result(state_root, auth)

    cas_transition(
        state_root,
        run_id=run_id,
        kind="fix",
        attempt_id=attempt_id,
        bundle_id=bundle_id,
        from_state="remote_pending",
        to_state="succeeded",
        commit_sha=validated.commit_sha,
        pr_number=pr_number,
        pr_url=pr_url,
    )

    try:
        post_issue_comment(
            project,
            approval.issue_id,
            (
                f"## Publish complete\n\n"
                f"Independent CT103 validation passed.\n\n"
                f"- Branch: `{agent_branch}`\n"
                f"- Commit: `{validated.commit_sha}`\n"
                f"- PR: #{pr_number}\n"
                f"- Bundle: `{bundle_id}`\n\n"
                f"Verification:\n"
                f"- claim: CT102 required workflows for published agent commit\n"
                f"  scope: commit `{validated.commit_sha}`\n"
                f"  command: .gitea/workflows/ci.yaml\n"
                f"  source: ct102\n"
                f"  status: requested\n"
                f"  artifact: pending_ci:{run_id}\n"
                f"  limitations: Publish succeeded; CI not yet terminal. Not fixed_verified.\n"
            ),
            settings=settings,
        )
    except Exception:
        # Comment failure must not mark publication failed
        pass

    from agent_control.session.verification import request_session_verification

    request_session_verification(
        state_root,
        project=project,
        run_id=run_id,
        commit_sha=validated.commit_sha,
    )

    from agent_control.publish.pdp import record_published_transaction

    record_published_transaction(
        state_root,
        pdp,
        pr_number=pr_number,
        commit_sha=validated.commit_sha,
    )

    return {
        "ok": True,
        "publish_state": "succeeded",
        "commit_sha": validated.commit_sha,
        "pr_number": pr_number,
        "pr_url": pr_url,
        "decision": "AUTO_ADMIT",
        "capability_id": (
            pdp.capability.capability_id if getattr(pdp, "capability", None) else None
        ),
    }


def broker_publish_repair(
    *,
    state_root: Path,
    run_id: str,
    attempt_id: str,
    bundle_id: str,
    expected_head_commit_sha: str,
    agent_branch: str,
    project: str,
    allowed_files: list[str],
    repo_url: str | None = None,
    settings: Settings | None = None,
) -> dict:
    """Repair brokerage: validate against trusted expected SHA; non-force FF push."""
    settings = settings or get_settings()
    record = load_publish_record(state_root, run_id, bundle_id)
    if record and record.publish_state == "succeeded":
        return {"ok": True, "idempotent": True}

    # Same publish_state machine as fix: queued → validating → remote_pending → succeeded.
    cas_transition(
        state_root,
        run_id=run_id,
        kind="repair",
        attempt_id=attempt_id,
        bundle_id=bundle_id,
        from_state="queued",
        to_state="validating",
        project=project,
        agent_branch=agent_branch,
    )

    try:
        manifest, bundle_root = load_ready_bundle(
            state_root,
            run_id=run_id,
            kind="repair",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
        )
        from agent_control.publish.eligibility import evaluate_publish_eligible

        eligibility = evaluate_publish_eligible(
            bundle_dir=bundle_root,
            manifest=manifest,
            require_attestations=True,
        )
        if not eligibility.eligible:
            cas_transition(
                state_root,
                run_id=run_id,
                kind="repair",
                attempt_id=attempt_id,
                bundle_id=bundle_id,
                from_state="validating",
                to_state="rejected",
                messages=eligibility.reason_codes + eligibility.messages,
            )
            _terminalize_broker_reject(
                state_root,
                project=project,
                run_id=run_id,
                broker_reason="attestation_gate",
                detail=eligibility.reason_codes,
            )
            return {
                "ok": False,
                "reason": "attestation_gate",
                "detail": eligibility.reason_codes,
            }
        snapshot = copy_bundle_to_snapshot(
            state_root,
            run_id=run_id,
            kind="repair",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
        )
    except BundleError as exc:
        cas_transition(
            state_root,
            run_id=run_id,
            kind="repair",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
            from_state="validating",
            to_state="rejected",
            messages=[str(exc)],
        )
        _terminalize_broker_reject(
            state_root,
            project=project,
            run_id=run_id,
            broker_reason="bundle_invalid",
            detail=[str(exc)],
        )
        return {"ok": False, "reason": "bundle_invalid", "detail": str(exc)}

    if manifest.producer_base_sha != expected_head_commit_sha:
        cas_transition(
            state_root,
            run_id=run_id,
            kind="repair",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
            from_state="validating",
            to_state="rejected",
            messages=["producer_base_sha != trusted expected head"],
        )
        _terminalize_broker_reject(
            state_root,
            project=project,
            run_id=run_id,
            broker_reason="base_sha_mismatch",
        )
        return {
            "ok": False,
            "reason": "base_sha_mismatch",
            "detail": "producer_base_sha != trusted expected head",
        }

    owner, repo = split_project(project)
    url = repo_url or f"{settings.gitea_base_url.rstrip('/')}/{owner}/{repo}.git"

    from agent_control.ci.repair_policy import decide_repair_repository

    publish_decision = decide_repair_repository(
        project,
        allowlist_raw=settings.fix_ci_repair_allowed_repos,
        allowed_classes_raw=settings.fix_ci_repair_allowed_classes,
        publish_enabled=settings.fix_ci_repair_publish_enabled,
        for_publish=True,
    )
    if not publish_decision.allowed:
        cas_transition(
            state_root,
            run_id=run_id,
            kind="repair",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
            from_state="validating",
            to_state="rejected",
            messages=[publish_decision.reason_code],
        )
        _terminalize_broker_reject(
            state_root,
            project=project,
            run_id=run_id,
            broker_reason=publish_decision.reason_code,
            detail=[publish_decision.reason_code],
        )
        return {
            "ok": False,
            "reason": "repair_repo_policy",
            "detail": publish_decision.reason_code,
        }

    # Synthetic binding for gate scope
    # Repair is not plan-bound; omit blast hash so the closed-world gate skips
    # plan/blast consistency (still enforces allowlist + other gate rules).
    binding = FixAuthorizationBinding(
        approval_id="repair",
        approval_target_id="repair",
        plan_run_id=run_id,
        plan_hash="repair",
        blast_radius_hash="",
        allowed_files=list(allowed_files),
        approved_base_sha=expected_head_commit_sha,
    )

    from agent_control.session.storage import load_session_by_run as _load_session_by_run

    repair_session = _load_session_by_run(state_root, project, run_id)
    repair_invoker = (repair_session.invoked_by if repair_session else None) or "unknown"
    pdp, pdp_reject = _run_broker_pdp(
        state_root=state_root,
        project=project,
        run_id=run_id,
        attempt_id=attempt_id,
        bundle_id=bundle_id,
        bundle_root=bundle_root,
        manifest=manifest,
        authorized_files=list(allowed_files),
        source_sha=expected_head_commit_sha,
        agent_branch=agent_branch,
        invoked_by=repair_invoker,
        kind="repair",
        record=record,
    )
    if pdp_reject is not None:
        return pdp_reject

    from agent_control.transaction.barriers import (
        DurableBarrierError as _RepairBarrierError,
        PHASE_PUBLISH as _REPAIR_PUBLISH,
        check_durable_effect_allowed as _check_repair_publish,
    )

    try:
        _check_repair_publish(state_root, run_id=run_id, phase=_REPAIR_PUBLISH)
    except _RepairBarrierError as exc:
        cas_transition(
            state_root,
            run_id=run_id,
            kind="repair",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
            from_state="validating",
            to_state="rejected",
            messages=[exc.code],
        )
        _terminalize_broker_reject(
            state_root,
            project=project,
            run_id=run_id,
            broker_reason=exc.code.lower(),
            detail=[exc.code],
        )
        return {"ok": False, "reason": exc.code, "published": False}

    try:
        validated = validate_and_commit(
            settings=settings,
            snapshot_dir=snapshot,
            manifest=manifest,
            binding=binding,
            repo_url=url,
            trusted_base_sha=expected_head_commit_sha,
            commit_message=f"agent(repair): {run_id} ({bundle_id})",
        )
    except ValidationError as exc:
        cas_transition(
            state_root,
            run_id=run_id,
            kind="repair",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
            from_state="validating",
            to_state="rejected",
            messages=[f"{exc.reason}: {exc}"],
        )
        _terminalize_broker_reject(
            state_root,
            project=project,
            run_id=run_id,
            broker_reason=exc.reason,
            detail=[str(exc)],
        )
        return {"ok": False, "reason": exc.reason, "detail": str(exc)}

    from agent_control.publish.pdp import witness_and_consume as _witness_and_consume
    from agent_control.transaction.capability import CAPABILITY_ALREADY_CONSUMED as _ALREADY

    consume = _witness_and_consume(
        pdp,
        current_base_sha=expected_head_commit_sha,
        patch_digest=validated.patch_sha256,
        repo=project,
        target_ref=agent_branch,
        policy_digest=pdp.policy.policy_digest,
    )
    if not consume.get("allowed"):
        status = str(consume.get("status") or "STATE_WITNESS")
        cas_transition(
            state_root,
            run_id=run_id,
            kind="repair",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
            from_state="validating",
            to_state="rejected",
            messages=[status, *list(consume.get("reasons") or [])],
        )
        _terminalize_broker_reject(
            state_root,
            project=project,
            run_id=run_id,
            broker_reason=(
                "capability_consume_failed"
                if status == _ALREADY
                else "state_witness_failed"
            ),
            detail=list(consume.get("reasons") or [status]),
        )
        return {
            "ok": False,
            "reason": status,
            "detail": consume.get("reasons"),
            "published": False,
        }

    # Supersede intent before push
    from agent_control.publish.state import load_publish_intent as _load_repair_intent
    from agent_control.transaction.ledger import record_publish_requested as _record_repair_publish

    existing_repair_intent = _load_repair_intent(state_root, project, validated.commit_sha)
    _record_repair_publish(
        state_root,
        project=project,
        transaction_id=str(getattr(pdp, "transaction_id", None) or run_id),
        capability_id=(
            pdp.capability.capability_id if getattr(pdp, "capability", None) else None
        ),
        patch_digest=str(getattr(pdp, "patch_digest", None) or validated.patch_sha256),
        repo=project,
        source_sha=expected_head_commit_sha,
        target_branch=agent_branch,
        expected_commit_sha=validated.commit_sha,
        run_id=run_id,
        bundle_id=bundle_id,
        kind="repair",
        publish_effect_id=(
            existing_repair_intent.publish_effect_id if existing_repair_intent else None
        ),
    )
    register_pending_ci(
        state_root,
        fix_run_id=run_id,
        repository=project,
        expected_head_commit_sha=validated.commit_sha,
        agent_branch=agent_branch,
    )

    cas_transition(
        state_root,
        run_id=run_id,
        kind="repair",
        attempt_id=attempt_id,
        bundle_id=bundle_id,
        from_state="validating",
        to_state="remote_pending",
        expected_commit_sha=validated.commit_sha,
        trusted_base_sha=expected_head_commit_sha,
        patch_sha256=validated.patch_sha256,
        result_tree_sha=validated.result_tree_sha,
        agent_branch=agent_branch,
        commit_sha=validated.commit_sha,
    )

    push = push_repair_fast_forward(
        workspace=validated.workspace,
        commit_sha=validated.commit_sha,
        agent_branch=agent_branch,
        expected_remote_sha=expected_head_commit_sha,
        repository=project,
        repo_url=url,
        settings=settings,
    )
    if not push.get("ok"):
        cas_transition(
            state_root,
            run_id=run_id,
            kind="repair",
            attempt_id=attempt_id,
            bundle_id=bundle_id,
            from_state="remote_pending",
            to_state="failed_terminal" if push.get("stale") else "failed_retryable",
            messages=[str(push.get("reason") or "push_failed")],
        )
        _terminalize_broker_reject(
            state_root,
            project=project,
            run_id=run_id,
            broker_reason="stale_base" if push.get("stale") else "push_failed",
            detail=[str(push.get("reason") or "push_failed")],
        )
        return {
            "ok": False,
            "stale": bool(push.get("stale")),
            "reason": push.get("reason") or "push_failed",
            "detail": push,
        }

    # Durable repair-pushed + pending supersede (CT103 authority)
    from agent_control.ci.events import append_fix_ci_repair_pushed
    from agent_shared.models.ci import FixCiRepairPushedEvent, RequiredWorkflow

    append_fix_ci_repair_pushed(
        state_root,
        FixCiRepairPushedEvent(
            fix_run_id=run_id,
            repository=project,
            previous_head_commit_sha=expected_head_commit_sha,
            new_head_commit_sha=validated.commit_sha,
            pr_number=None,
            repair_attempt=int(attempt_id) if str(attempt_id).isdigit() else 1,
            repair_key=f"{project}:{run_id}:{attempt_id}",
        ),
    )
    register_pending_ci(
        state_root,
        fix_run_id=run_id,
        repository=project,
        expected_head_commit_sha=validated.commit_sha,
        agent_branch=agent_branch,
        required_workflows=[
            RequiredWorkflow(path=".gitea/workflows/ci.yaml", source="repo_default")
        ],
    )

    auth = AuthoritativePublishResult(
        run_id=run_id,
        bundle_id=bundle_id,
        attempt_id=attempt_id,
        kind="repair",
        trusted_base_sha=expected_head_commit_sha,
        patch_sha256=validated.patch_sha256,
        result_tree_sha=validated.result_tree_sha,
        commit_sha=validated.commit_sha,
        remote_branch=agent_branch,
        published_at=_now(),
        publish_state="succeeded",
    )
    _write_auth_result(state_root, auth)
    cas_transition(
        state_root,
        run_id=run_id,
        kind="repair",
        attempt_id=attempt_id,
        bundle_id=bundle_id,
        from_state="remote_pending",
        to_state="succeeded",
        commit_sha=validated.commit_sha,
        agent_branch=agent_branch,
    )

    from agent_control.session.verification import request_session_verification

    request_session_verification(
        state_root,
        project=project,
        run_id=run_id,
        commit_sha=validated.commit_sha,
    )

    from agent_control.publish.pdp import record_published_transaction as _record_published

    _complete_broker_capability(pdp)
    _record_published(
        state_root,
        pdp,
        pr_number=None,
        commit_sha=validated.commit_sha,
    )

    return {
        "ok": True,
        "new_head_commit_sha": validated.commit_sha,
        "publish_state": "succeeded",
        "decision": "AUTO_ADMIT",
        "capability_id": (
            pdp.capability.capability_id if getattr(pdp, "capability", None) else None
        ),
    }
