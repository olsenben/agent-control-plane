"""Terminal workflow_run observe + API confirm (Slice 6E.1)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_control.ci.aggregate import (
    evaluate_aggregate,
    merge_observation,
    normalize_conclusion,
    result_from_pending,
)
from agent_control.ci.artifacts import (
    load_verification_current,
    write_observation_artifact,
    write_verification_current,
)
from agent_control.ci.comments import post_ci_status_comment
from agent_control.ci.events import append_fix_ci_observed, append_fix_ci_verdict_changed
from agent_control.ci.pending import find_pending_by_repo_sha, save_pending_ci
from agent_control.config import Settings, get_settings
from agent_control.gitea_client import GiteaClient
from agent_shared.models.ci import (
    CiVerificationResult,
    FixCiObservedEvent,
    FixCiVerdictChangedEvent,
    RequiredWorkflow,
    WorkflowObservation,
)
from agent_shared.repo_identity import split_repo_full_name

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = frozenset({"completed", "success", "failure"})


def fix_ci_observe_enabled(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return bool(settings.fix_ci_observe_enabled)


def extract_workflow_run_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize webhook payload fields (Phase 0 contract)."""
    run = payload.get("workflow_run") or payload.get("workflow_job") or {}
    repo = payload.get("repository") or {}
    head_sha = (
        run.get("head_sha")
        or run.get("head_commit", {}).get("id")
        or run.get("commit_sha")
        or ""
    )
    prs = run.get("pull_requests") or []
    pr_number = None
    if prs and isinstance(prs[0], dict):
        pr_number = prs[0].get("number")
    return {
        "repository": repo.get("full_name") or "",
        "workflow_run_id": str(run.get("id") or run.get("run_id") or ""),
        "run_attempt": int(run.get("run_attempt") or run.get("attempt") or 1),
        "status": str(run.get("status") or ""),
        "conclusion": run.get("conclusion"),
        "head_sha": str(head_sha or ""),
        "workflow_id": str(run.get("workflow_id") or "") or None,
        "path": str(run.get("path") or run.get("workflow_path") or ""),
        "display_name": str(
            run.get("name") or run.get("display_title") or run.get("workflow_name") or ""
        ),
        "pr_number": int(pr_number) if pr_number is not None else None,
        "html_url": run.get("html_url"),
        "event": run.get("event"),
    }


def is_terminal_workflow_payload(payload: dict[str, Any]) -> bool:
    fields = extract_workflow_run_fields(payload)
    status = fields["status"].lower()
    conclusion = fields["conclusion"]
    if status in _TERMINAL_STATUSES or status == "completed":
        return True
    if conclusion is not None and str(conclusion).strip():
        return True
    return False


def _confirm_via_api(
    client: GiteaClient,
    repository: str,
    workflow_run_id: str,
    webhook_fields: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    """Fetch authoritative run; return (api_fields, api_verification_status)."""
    owner, repo = split_repo_full_name(repository)
    try:
        data = client.get_workflow_run(owner, repo, workflow_run_id)
    except Exception as exc:
        logger.warning(
            "ci_api_unavailable run_id=%s err=%s",
            workflow_run_id,
            exc,
        )
        return webhook_fields, "unavailable"

    api_fields = {
        "repository": repository,
        "workflow_run_id": str(data.get("id") or workflow_run_id),
        "run_attempt": int(data.get("run_attempt") or data.get("attempt") or 1),
        "status": str(data.get("status") or ""),
        "conclusion": data.get("conclusion"),
        "head_sha": str(
            data.get("head_sha")
            or data.get("head_commit", {}).get("id")
            or data.get("commit_sha")
            or ""
        ),
        "workflow_id": str(data.get("workflow_id") or "") or None,
        "path": str(data.get("path") or data.get("workflow_path") or ""),
        "display_name": str(data.get("name") or data.get("display_title") or ""),
        "pr_number": webhook_fields.get("pr_number"),
    }
    # Trust API when it contradicts webhook
    contradictions = []
    for key in ("head_sha", "status", "conclusion", "run_attempt"):
        wh = webhook_fields.get(key)
        ap = api_fields.get(key)
        if wh is not None and ap is not None and str(wh) != str(ap):
            contradictions.append(key)
    status = "contradicted" if contradictions else "confirmed"
    return api_fields, status


def required_workflows_from_hints(
    workflows: list[str],
    *,
    require_matrix: bool,
    repo_default: str | None = None,
) -> list[RequiredWorkflow]:
    required: list[RequiredWorkflow] = []
    for item in workflows:
        text = (item or "").strip()
        if not text:
            continue
        if ".gitea/workflows/" in text or text.endswith((".yml", ".yaml")):
            required.append(
                RequiredWorkflow(path=text.replace("\\", "/"), display_name=text, source="matrix")
            )
        else:
            required.append(RequiredWorkflow(display_name=text, path="", source="matrix"))
    if not required and require_matrix and repo_default:
        required.append(
            RequiredWorkflow(
                path=repo_default,
                display_name=repo_default,
                source="repo_default",
            )
        )
    return required


def apply_observation(
    state_root: Path,
    *,
    repository: str,
    head_sha: str,
    observation: WorkflowObservation,
    settings: Settings | None = None,
    post_comment: bool = True,
) -> CiVerificationResult | None:
    """Correlate by repo+exact SHA, merge observation, emit append-only events."""
    settings = settings or get_settings()
    pending = find_pending_by_repo_sha(state_root, repository, head_sha)
    if pending is None:
        # V4.1.1: accept CI when publish intent exists (race before pending finalize)
        from agent_control.publish.state import find_intent_by_repo_sha

        intent = find_intent_by_repo_sha(state_root, repository, head_sha)
        if intent is None:
            logger.info(
                "ci_no_pending repo=%s sha=%s",
                repository,
                head_sha[:12] if head_sha else "",
            )
            return None
        # Materialize a minimal pending from intent so observation can proceed
        from agent_control.ci.pending import register_pending_ci

        pending = register_pending_ci(
            state_root,
            fix_run_id=intent.run_id,
            repository=repository,
            expected_head_commit_sha=head_sha,
            agent_branch=intent.agent_branch,
        )
    if pending.current_verdict in ("superseded", "expired"):
        return None

    # Exact SHA already enforced by find; refuse PR-number-only mismatch
    if observation.pr_number is not None and pending.opened_pr_number is not None:
        if observation.pr_number != pending.opened_pr_number:
            # Supporting evidence mismatch — still allow if SHA matches (plan: PR is supporting only)
            logger.info(
                "ci_pr_mismatch_ignored fix_run_id=%s obs_pr=%s pending_pr=%s",
                pending.fix_run_id,
                observation.pr_number,
                pending.opened_pr_number,
            )

    artifact_root = Path(pending.artifact_root) if pending.artifact_root else None
    result = None
    if artifact_root and artifact_root.is_dir():
        result = load_verification_current(artifact_root)
    if result is None:
        result = result_from_pending(pending)

    previous_verdict = result.verdict
    previous_revision = result.verdict_revision
    result = merge_observation(result, observation)

    # Artifacts (failure observable, non-fatal for ledger)
    if artifact_root is not None:
        try:
            write_observation_artifact(artifact_root, observation)
            write_verification_current(artifact_root, result)
        except OSError:
            logger.exception(
                "ci_artifact_write_failed fix_run_id=%s",
                pending.fix_run_id,
            )

    append_fix_ci_observed(
        state_root,
        FixCiObservedEvent(
            fix_run_id=pending.fix_run_id,
            repository=pending.repository,
            expected_head_commit_sha=pending.expected_head_commit_sha,
            observation=observation,
            delivery_id=observation.delivery_id,
        ),
    )

    if result.verdict != previous_verdict or result.verdict_revision != previous_revision:
        append_fix_ci_verdict_changed(
            state_root,
            FixCiVerdictChangedEvent(
                fix_run_id=pending.fix_run_id,
                repository=pending.repository,
                expected_head_commit_sha=pending.expected_head_commit_sha,
                previous_verdict=previous_verdict,  # type: ignore[arg-type]
                verdict=result.verdict,
                verdict_revision=result.verdict_revision,
                reason_codes=list(result.reason_codes),
                evaluated_at=result.evaluated_at,
            ),
        )

    pending.current_verdict = result.verdict
    pending.verdict_revision = result.verdict_revision
    save_pending_ci(state_root, pending)

    if post_comment and result.verdict != previous_verdict:
        post_ci_status_comment(result, settings=settings)

    # 6F.1: ensure failure evidence for each terminal failing required-workflow observation
    evidence_manifest = None
    if (
        artifact_root is not None
        and settings.fix_ci_failure_evidence_enabled
        and observation.conclusion
        in ("failure", "cancelled", "timed_out", "unknown")
    ):
        from agent_control.ci.evidence_comments import post_failure_evidence_comment
        from agent_control.ci.events import (
            append_fix_ci_failure_evidence_collected,
            append_fix_ci_failure_evidence_unavailable,
        )
        from agent_control.ci.failure_evidence import (
            ensure_failure_evidence,
            failure_evidence_dir,
        )
        from agent_shared.models.ci import (
            FixCiFailureEvidenceCollectedEvent,
            FixCiFailureEvidenceUnavailableEvent,
        )

        try:
            evidence_manifest = ensure_failure_evidence(
                artifact_root,
                fix_run_id=pending.fix_run_id,
                repository=pending.repository,
                expected_head_sha=pending.expected_head_commit_sha,
                observation=observation,
                settings=settings,
            )
            if evidence_manifest.status == "collected":
                append_fix_ci_failure_evidence_collected(
                    state_root,
                    FixCiFailureEvidenceCollectedEvent(
                        fix_run_id=pending.fix_run_id,
                        repository=pending.repository,
                        expected_head_commit_sha=pending.expected_head_commit_sha,
                        pr_number=observation.pr_number or pending.opened_pr_number,
                        evidence_observation_id=evidence_manifest.evidence_observation_id,
                        workflow_run_id=observation.workflow_run_id,
                        workflow_run_attempt=observation.run_attempt,
                        status="collected",
                        failure_class=evidence_manifest.failure_class,
                        has_terminal_failed_job=evidence_manifest.has_terminal_failed_job,
                    ),
                )
            else:
                append_fix_ci_failure_evidence_unavailable(
                    state_root,
                    FixCiFailureEvidenceUnavailableEvent(
                        fix_run_id=pending.fix_run_id,
                        repository=pending.repository,
                        expected_head_commit_sha=pending.expected_head_commit_sha,
                        pr_number=observation.pr_number or pending.opened_pr_number,
                        evidence_observation_id=evidence_manifest.evidence_observation_id,
                        workflow_run_id=observation.workflow_run_id,
                        workflow_run_attempt=observation.run_attempt,
                        status=evidence_manifest.status,
                        reason_codes=list(evidence_manifest.reason_codes),
                    ),
                )
            if post_comment:
                excerpt = ""
                if evidence_manifest.status == "collected" and evidence_manifest.jobs:
                    job_path = (
                        failure_evidence_dir(
                            artifact_root,
                            evidence_manifest.evidence_observation_id,
                        )
                        / "jobs"
                        / f"{evidence_manifest.jobs[0].job_id}.txt"
                    )
                    if job_path.is_file():
                        excerpt = job_path.read_text(encoding="utf-8", errors="replace")[:1200]
                post_failure_evidence_comment(
                    result,
                    evidence_manifest,
                    excerpt=excerpt,
                    settings=settings,
                )
        except Exception:
            logger.exception(
                "ci_failure_evidence_failed fix_run_id=%s run=%s",
                pending.fix_run_id,
                observation.workflow_run_id,
            )

    # 6F.2: consider repair only after aggregate gating (flag default off)
    repair_requested = False
    if settings.fix_ci_repair_enabled and result.verdict == "failing":
        from pathlib import Path as _Path

        from agent_control.aci.backends import get_sandbox_backend
        from agent_control.ci.events import (
            append_fix_ci_repair_blocked,
            append_fix_ci_repair_requested,
        )
        from agent_control.ci.repair import consider_repair_dispatch, release_pr_lock
        from agent_control.ci.reservation import save_repair_reservation
        from agent_control.queue import enqueue_ci_repair
        from agent_control.sandbox.command_runner import required_command_ids_for_failure_class
        from agent_shared.models.ci import FixCiRepairBlockedEvent, FixCiRepairRequestedEvent

        branch = pending.agent_branch or ""
        branch_ok = branch.startswith("agent/")
        backend = get_sandbox_backend(
            settings.sandbox_backend,
            expected_policy_hash=settings.sandbox_expected_policy_hash or None,
        )
        ws = artifact_root if artifact_root is not None else state_root / "tmp-sandbox"
        ws.mkdir(parents=True, exist_ok=True)
        attestation = backend.attest(
            workspace=ws,
            policy_hash=settings.sandbox_expected_policy_hash
            or __import__(
                "agent_control.aci.backends.probes", fromlist=["policy_hash"]
            ).policy_hash(),
        )
        failure_class = evidence_manifest.failure_class if evidence_manifest else "unknown"
        required_ids = required_command_ids_for_failure_class(failure_class)
        from agent_control.ci.scope import resolve_allowed_files_for_fix

        allowed_files = resolve_allowed_files_for_fix(
            state_root,
            repository=pending.repository,
            fix_run_id=pending.fix_run_id,
            issue_id=pending.issue_id,
        )
        if failure_class in __import__(
            "agent_shared.models.ci", fromlist=["AUTO_REPAIRABLE_FAILURE_CLASSES"]
        ).AUTO_REPAIRABLE_FAILURE_CLASSES and not required_ids:
            append_fix_ci_repair_blocked(
                state_root,
                FixCiRepairBlockedEvent(
                    fix_run_id=pending.fix_run_id,
                    repository=pending.repository,
                    expected_head_commit_sha=pending.expected_head_commit_sha,
                    pr_number=pending.opened_pr_number,
                    reason_codes=["no_mapped_verifier"],
                    label="agent:blocked",
                ),
            )
        else:
            current_pr_head = pending.expected_head_commit_sha
            try:
                from agent_control.gitea_client import GiteaClient
                from agent_shared.repo_identity import split_repo_full_name

                owner, repo = split_repo_full_name(pending.repository)
                if pending.agent_branch:
                    tip = GiteaClient(settings).get_branch_sha(
                        owner, repo, pending.agent_branch
                    )
                    if tip:
                        current_pr_head = tip
            except Exception:
                logger.exception(
                    "ci_repair_head_fetch_failed fix_run_id=%s", pending.fix_run_id
                )

            dispatch = consider_repair_dispatch(
                state_root,
                result=result,
                pending=pending,
                evidence=evidence_manifest,
                attestation=attestation,
                current_pr_head=current_pr_head,
                branch_ok=branch_ok,
                no_unrecognized_commits=True,
                allowed_files=allowed_files,
                required_command_ids=required_ids,
                settings=settings,
            )
            lock_path = (
                _Path(str(dispatch["lock_path"])) if dispatch.get("lock_path") else None
            )
            try:
                if dispatch.get("blocked"):
                    # reservation_exists is not a new blocked event (dedupe)
                    if "reservation_exists" in (dispatch.get("reason_codes") or []):
                        repair_requested = True
                    if "reservation_exists" not in (dispatch.get("reason_codes") or []):
                        append_fix_ci_repair_blocked(
                            state_root,
                            FixCiRepairBlockedEvent(
                                fix_run_id=pending.fix_run_id,
                                repository=pending.repository,
                                expected_head_commit_sha=pending.expected_head_commit_sha,
                                pr_number=pending.opened_pr_number,
                                reason_codes=list(dispatch.get("reason_codes") or []),
                                label=str(dispatch.get("label") or "agent:blocked"),
                            ),
                        )
                elif dispatch.get("dispatched"):
                    reservation = dispatch.get("reservation") or {}
                    # Automatic repair stays in the fix session (append run_id).
                    repair_run_id = (
                        f"run-repair-{pending.fix_run_id}-"
                        f"{int(dispatch.get('repair_attempt') or 0)}"
                    )
                    session_id = None
                    try:
                        from agent_control.session import (
                            append_run_to_session,
                            begin_typed_session,
                            load_session_by_run,
                        )

                        fix_session = load_session_by_run(
                            state_root, pending.repository, pending.fix_run_id
                        )
                        if fix_session is not None:
                            fix_session = append_run_to_session(
                                state_root, fix_session, run_id=repair_run_id
                            )
                            session_id = fix_session.session_id
                            try:
                                from agent_control.session.prepare_dispatch import (
                                    attach_preflight_for_non_rlm_session,
                                )

                                tc = {
                                    "author": "ci_repair",
                                    "issue_number": pending.issue_id,
                                    "pr_number": pending.opened_pr_number,
                                }
                                attach_preflight_for_non_rlm_session(
                                    state_root,
                                    fix_session,
                                    run_id=repair_run_id,
                                    source_sha=pending.expected_head_commit_sha or "",
                                    trigger_context=tc,
                                    settings=settings,
                                )
                            except Exception:
                                logger.exception(
                                    "repair_preflight_failed fix_run_id=%s",
                                    pending.fix_run_id,
                                )
                        else:
                            # No fix session (legacy) — create repair session.
                            tc = {
                                "author": "ci_repair",
                                "issue_number": pending.issue_id,
                                "pr_number": pending.opened_pr_number,
                            }
                            created = begin_typed_session(
                                state_root,
                                project=pending.repository,
                                command_kind="repair",
                                run_id=repair_run_id,
                                head_sha=pending.expected_head_commit_sha or "",
                                trigger_context=tc,
                            )
                            session_id = created.session_id
                            try:
                                from agent_control.session.prepare_dispatch import (
                                    attach_preflight_for_non_rlm_session,
                                )

                                attach_preflight_for_non_rlm_session(
                                    state_root,
                                    created,
                                    run_id=repair_run_id,
                                    source_sha=pending.expected_head_commit_sha or "",
                                    trigger_context=tc,
                                    settings=settings,
                                )
                            except Exception:
                                logger.exception(
                                    "repair_preflight_failed fix_run_id=%s",
                                    pending.fix_run_id,
                                )
                    except Exception:
                        logger.exception(
                            "repair_session_bind_failed fix_run_id=%s",
                            pending.fix_run_id,
                        )

                    job_payload = {
                        "schema_version": "ci_repair_job.v1",
                        "state_root": str(state_root),
                        "session_id": session_id,
                        "run_id": repair_run_id,
                        **reservation,
                    }
                    job_id = enqueue_ci_repair(settings.redis_url, job_payload)
                    if not job_id:
                        # Do not emit requested without a durable job
                        from agent_control.ci.reservation import (
                            load_repair_reservation,
                            reservation_path,
                        )

                        existing = load_repair_reservation(
                            state_root, str(dispatch.get("repair_key") or "")
                        )
                        if existing and existing.status == "reserved" and not existing.job_id:
                            path = reservation_path(state_root, existing.repair_key)
                            path.unlink(missing_ok=True)
                        append_fix_ci_repair_blocked(
                            state_root,
                            FixCiRepairBlockedEvent(
                                fix_run_id=pending.fix_run_id,
                                repository=pending.repository,
                                expected_head_commit_sha=pending.expected_head_commit_sha,
                                pr_number=pending.opened_pr_number,
                                reason_codes=["dispatch_failed"],
                                label="agent:blocked",
                            ),
                        )
                    else:
                        from agent_control.ci.reservation import load_repair_reservation

                        existing = load_repair_reservation(
                            state_root, str(dispatch.get("repair_key") or "")
                        )
                        if existing:
                            existing.job_id = job_id
                            save_repair_reservation(state_root, existing)
                        append_fix_ci_repair_requested(
                            state_root,
                            FixCiRepairRequestedEvent(
                                fix_run_id=pending.fix_run_id,
                                repository=pending.repository,
                                expected_head_commit_sha=pending.expected_head_commit_sha,
                                pr_number=pending.opened_pr_number,
                                evidence_observation_id=(
                                    evidence_manifest.evidence_observation_id
                                    if evidence_manifest
                                    else ""
                                ),
                                repair_attempt=int(dispatch.get("repair_attempt") or 0),
                                repair_key=str(dispatch.get("repair_key") or ""),
                            ),
                        )
                        repair_requested = True
            finally:
                release_pr_lock(lock_path)

    # 6E.2 memory on verified
    if result.verdict == "verified" and previous_verdict != "verified":
        from agent_control.ci.memory import writeback_fix_ci_verified

        writeback_fix_ci_verified(
            state_root,
            pending=pending,
            result=result,
            settings=settings,
        )

    # Slice 5.6: session verification gate (defer finish until CI terminal)
    if result.verdict != previous_verdict or result.verdict in (
        "verified",
        "failing",
        "expired",
    ):
        from agent_control.session.verification import apply_ci_verdict_to_session

        apply_ci_verdict_to_session(
            state_root,
            project=pending.repository,
            fix_run_id=pending.fix_run_id,
            verdict=result.verdict,
            previous_verdict=previous_verdict,
            expected_head_commit_sha=pending.expected_head_commit_sha,
            verdict_revision=result.verdict_revision,
            artifact=(
                f"ci_verification:{pending.fix_run_id}:rev{result.verdict_revision}"
            ),
            defer_fail_for_repair=repair_requested,
        )

    # T08: bounded recursive Qwen loop decision (evidence-selected; no 6F.2 enable)
    if result.verdict in ("failing", "verified"):
        try:
            from agent_control.qwen_loop.observe_hook import record_ci_grounded_qwen_loop

            record_ci_grounded_qwen_loop(
                state_root,
                repository=pending.repository,
                fix_run_id=pending.fix_run_id,
                ci_verdict=result.verdict,
                evidence=evidence_manifest,
                settings=settings,
            )
        except Exception:
            logger.exception(
                "qwen_loop_record_failed fix_run_id=%s verdict=%s",
                pending.fix_run_id,
                result.verdict,
            )

    return result


def handle_workflow_event(
    state_root: Path,
    event: dict[str, Any],
    *,
    settings: Settings | None = None,
    gitea_client: GiteaClient | None = None,
) -> dict[str, Any]:
    """Process terminal gitea.workflow_* ledger event."""
    settings = settings or get_settings()
    if not fix_ci_observe_enabled(settings):
        return {"handled": False, "reason": "fix_ci_observe_disabled"}

    etype = event.get("type", "")
    if not etype.startswith("gitea.workflow_"):
        return {"handled": False, "reason": "not_workflow_event"}

    # v1: terminal only (skip started)
    if etype == "gitea.workflow_started":
        return {"handled": False, "reason": "non_terminal"}

    payload = event.get("payload") or {}
    if not is_terminal_workflow_payload(payload):
        return {"handled": False, "reason": "non_terminal_payload"}

    fields = extract_workflow_run_fields(payload)
    repository = fields["repository"] or event.get("project") or ""
    head_sha = fields["head_sha"]
    if not repository or not head_sha or not fields["workflow_run_id"]:
        return {"handled": False, "reason": "missing_correlation_fields"}

    # Exact PR + wrong SHA must not correlate — find_pending_by_repo_sha enforces SHA
    client = gitea_client or GiteaClient(settings)
    api_fields, api_status = _confirm_via_api(
        client,
        repository,
        fields["workflow_run_id"],
        fields,
    )
    # Trust API
    trusted = api_fields
    conclusion = normalize_conclusion(
        trusted.get("conclusion"),
        status=str(trusted.get("status") or ""),
    )
    now = datetime.now(timezone.utc).isoformat()
    observation = WorkflowObservation(
        workflow_id=trusted.get("workflow_id"),
        path=str(trusted.get("path") or ""),
        display_name=str(trusted.get("display_name") or ""),
        workflow_run_id=str(trusted.get("workflow_run_id")),
        run_attempt=int(trusted.get("run_attempt") or 1),
        status=str(trusted.get("status") or ""),
        conclusion=conclusion,
        head_sha=str(trusted.get("head_sha") or ""),
        pr_number=trusted.get("pr_number"),
        delivery_id=event.get("delivery_id"),
        observed_at=now,
        api_verification_status=api_status,  # type: ignore[arg-type]
    )

    # If API SHA differs from webhook, use API SHA for correlation
    corr_sha = observation.head_sha or head_sha
    result = apply_observation(
        state_root,
        repository=repository,
        head_sha=corr_sha,
        observation=observation,
        settings=settings,
    )
    if result is None:
        return {
            "handled": False,
            "reason": "no_pending_match",
            "repository": repository,
            "head_sha": corr_sha,
        }
    return {
        "handled": True,
        "fix_run_id": result.fix_run_id,
        "verdict": result.verdict,
        "verdict_revision": result.verdict_revision,
        "api_verification_status": api_status,
    }


def rebuild_result_from_ledger(
    state_root: Path,
    repository: str,
    fix_run_id: str,
) -> Any:
    """Rebuild aggregate from append-only events (reconciler helper)."""
    from agent_control.ci.pending import load_pending_ci
    from agent_control.events import load_project_events

    pending = load_pending_ci(state_root, repository, fix_run_id)
    if pending is None:
        return None
    result = result_from_pending(pending)
    for event in load_project_events(state_root, repository):
        if event.get("type") != "agent.fix_ci_observed":
            continue
        payload = event.get("payload") or {}
        if payload.get("fix_run_id") != fix_run_id:
            continue
        obs_data = payload.get("observation") or {}
        try:
            obs = WorkflowObservation.model_validate(obs_data)
        except ValueError:
            continue
        result = merge_observation(result, obs)
    return evaluate_aggregate(result)
