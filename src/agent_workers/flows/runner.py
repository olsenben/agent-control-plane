"""CT104 flow session runner — deterministic job lifecycle."""

from __future__ import annotations

import json
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_shared.constants import (
    FIX_STATUS_PATCH_BUNDLE_READY,
    GITEA_COMMENT_SUMMARY_PROMPT_BUDGET_CHARS,
    PRODUCER_PROTOCOL_PATCH_BUNDLE_V1,
    TERMINAL_STATUS_COMPLETED,
    TERMINAL_STATUS_FAILED_APPLY,
    TERMINAL_STATUS_FAILED_GATE,
    TERMINAL_STATUS_FAILED_QUALITY_GATE,
    RunStatus,
    SessionEventType,
)
from agent_shared.models.jobs import RLMJob
from agent_shared.models.session import BootstrapInfo, RedactionReport, SystemContext
from agent_shared.bundles import BundleError
from agent_shared.git_patch import git_write_tree
from agent_workers.artifacts.session_events import SessionEventWriter
from agent_workers.artifacts.writer import (
    ensure_run_dir,
    initial_metadata,
    update_metadata_engine,
    update_metadata_status,
    write_json,
    write_metadata,
)
from agent_workers.context.broker import ContextBroker
from agent_workers.executor.lifecycle import (
    ExecutorLifecycle,
    resolve_runtime_attestation,
)
from agent_workers.flows.failure_report import (
    dispatch_report,
    finalize_failed_run,
    infer_terminal_status_from_artifacts,
)
from agent_workers.formatters.fix_comment import (
    render_fix_comment,
    render_fix_failed,
    render_fix_gate_failed,
    render_fix_quality_failed,
)
from agent_workers.gates.runner import APPROVED_PATCH_NAME, DiffGateError, run_closed_world_diff_gate
from agent_workers.patch.apply import ApplyFixError, apply_fix_to_workspace
from agent_workers.rlm.budget import fit_summary_for_comment
from agent_workers.rlm.output_quality import (
    evaluate_patch_artifact,
    write_quality_gate_result,
)
from agent_workers.rlm.engine import get_engine
from agent_workers.runtime.capabilities import detect_capabilities, python_version
from agent_workers.security.redactor import SecretRedactor
from agent_workers.repo.policy_loader import (
    PolicyWorkspaceError,
    checkout_pinned_policy_workspace,
    clone_repo,
    load_policy,
    write_policy_artifacts,
)
from agent_control.project_registry import pin_from_job_fields
from agent_workers.settings import WorkerSettings, get_worker_settings
from agent_workers.tools.registry import make_registry


def _write_fix_patch_bundle(
    *,
    repo_workspace: Path,
    run_path: Path,
    job: RLMJob,
    result,
    settings: WorkerSettings,
    session: SessionEventWriter,
    gate_result,
    lifecycle: ExecutorLifecycle,
) -> None:
    """CT104 producer: durable READY bundle + teardown + execution attestation."""
    patch_path = run_path / APPROVED_PATCH_NAME
    if not patch_path.is_file():
        result.fix_status = "worker_failed"
        return

    producer_base = None
    if job.fix_authorization:
        producer_base = job.fix_authorization.approved_base_sha
    producer_base = producer_base or getattr(job, "target_sha", None) or ""

    producer_tree: str | None = None
    try:
        producer_tree = git_write_tree(repo_workspace)
    except Exception:
        producer_tree = None

    gate_payload = None
    if gate_result is not None:
        gate_payload = (
            gate_result.model_dump(mode="json")
            if hasattr(gate_result, "model_dump")
            else gate_result
        )
    fix_payload = result.fix_result.model_dump(mode="json") if result.fix_result else None

    try:
        manifest = lifecycle.finalize_durable_bundle(
            settings.agent_state_root,
            kind="fix",
            attempt_id="1",
            producer_base_sha=producer_base,
            patch_bytes=patch_path.read_bytes(),
            producer_tree_sha=producer_tree,
            gate_snapshot=gate_payload,
            result_payload=fix_payload,
            artifact_dir=run_path,
        )
        lifecycle.final_target_head = producer_tree or ""
        lifecycle.teardown_workspace()
        lifecycle.write_execution_attestation(artifact_dir=run_path)
    except BundleError as exc:
        write_json(
            run_path / "error.json",
            {"stage": "bundle_write", "message": str(exc)},
        )
        result.status = "failed"
        result.fix_status = "worker_failed"
        result.summary = f"Failed to write patch bundle: {exc}"
        return
    except Exception as exc:
        write_json(
            run_path / "error.json",
            {"stage": "attestation_lifecycle", "message": str(exc)},
        )
        result.status = "failed"
        result.fix_status = "worker_failed"
        result.summary = f"Attestation lifecycle failed: {exc}"
        return

    result.fix_status = FIX_STATUS_PATCH_BUNDLE_READY
    result.producer_protocol = PRODUCER_PROTOCOL_PATCH_BUNDLE_V1
    result.bundle_id = manifest.bundle_id
    result.attempt_id = manifest.attempt_id
    result.bundle_kind = "fix"
    result.summary = fit_summary_for_comment(
        (
            render_fix_comment(
                result.fix_result,
                patch_artifact="patch.diff",
                ci_matrix=gate_result.selected_ci_matrix if gate_result else None,
            )
            + "\n\nLocal patch produced and queued for independent publication validation."
        ),
        GITEA_COMMENT_SUMMARY_PROMPT_BUDGET_CHARS,
    )
    session.emit(SessionEventType.ARTIFACT_WRITTEN, artifact=f"bundle:{manifest.bundle_id}")


def _context_sources_from_trace(trace_path: Path) -> list[str]:
    if not trace_path.exists():
        return []
    for line in reversed(trace_path.read_text(encoding="utf-8").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("event") == "context_gathered" and event.get("sources"):
            return list(event["sources"])
    return []


def run_flow_session(job_payload: dict[str, Any], settings: WorkerSettings | None = None) -> dict[str, Any]:
    settings = settings or get_worker_settings()
    job = RLMJob.model_validate(job_payload)
    run_path = ensure_run_dir(settings.agent_runs_dir, job.project, job.run_id)
    redactor = SecretRedactor()
    session_path = run_path / "session_events.jsonl"
    session = SessionEventWriter(session_path, job.run_id, redactor)
    meta_path = run_path / "metadata.json"

    try:
        session.emit(SessionEventType.RUN_CREATED)
        write_json(run_path / "input_job.json", job.model_dump(mode="json"))
        metadata = initial_metadata(job.model_dump(mode="json"))
        write_metadata(meta_path, metadata)

        session.emit(SessionEventType.BOOTSTRAP_STARTED)
        repo_workspace = run_path / "repo"
        policy_workspace = run_path / "policy_repo"
        pin = pin_from_job_fields(
            policy_source_repo=job.policy_source_repo,
            policy_source_remote=job.policy_source_remote,
            policy_source_ref=job.policy_source_ref,
            policy_source_sha=job.policy_source_sha,
            policy_schema_version=job.policy_schema_version,
            project=job.project,
            repo_url=job.repo_url,
            policy_ref=job.policy_ref,
        )
        if pin is None:
            raise PolicyWorkspaceError("job missing immutable policy_source_sha pin")
        checkout_pinned_policy_workspace(
            settings,
            pin,
            policy_workspace,
            clone_url=job.repo_url,
        )
        clone_repo(settings, job.repo_url, job.task_ref, repo_workspace)

        bootstrap = BootstrapInfo(
            run_id=job.run_id,
            worker="worker-rlm-root",
            queue="rlm-root",
            repo_url=job.repo_url,
            checkout_ref=job.task_ref,
            policy_ref=job.policy_source_ref or job.policy_ref,
            artifact_root=str(run_path),
            python_version=python_version(),
        )
        write_json(run_path / "bootstrap.json", bootstrap.model_dump(mode="json"))

        caps = detect_capabilities(settings, job.run_id, policy_workspace, job.model_policy)
        write_json(run_path / "capabilities.json", caps.model_dump(mode="json"))

        system_ctx = SystemContext(
            run_id=job.run_id,
            worker="worker-rlm-root",
            workspace=str(repo_workspace),
            available_tools=caps.model_endpoint and ["read_repo", "search_code"] or ["read_repo"],
            flow=job.flow,
            agent=job.agent,
        )
        write_json(run_path / "system_context.json", system_ctx.model_dump(mode="json"))
        session.emit(SessionEventType.BOOTSTRAP_COMPLETED)

        session.emit(SessionEventType.POLICY_LOAD_STARTED)
        policy_source, effective, warnings = load_policy(policy_workspace, job.model_dump(mode="json"), settings)
        write_policy_artifacts(run_path, policy_source, effective)
        if warnings:
            update_metadata_status(meta_path, RunStatus.POLICY_LOADED, warnings)
        else:
            update_metadata_status(meta_path, RunStatus.POLICY_LOADED)
        session.emit(SessionEventType.POLICY_LOAD_COMPLETED)

        producer_base = ""
        if job.fix_authorization:
            producer_base = job.fix_authorization.approved_base_sha or ""
        producer_base = producer_base or job.target_sha or ""

        lifecycle = ExecutorLifecycle(
            run_id=job.run_id,
            job_id=job.job_id,
            ct103_nonce=job.attestation_nonce or "",
            policy_source_repo=job.policy_source_repo,
            policy_source_sha=job.policy_source_sha,
            target_source_sha=producer_base,
            command_registry_hash=getattr(effective, "command_registry_hash", "") or "",
            effective_command_policy_hash=getattr(effective, "effective_command_policy_hash", "")
            or "",
            durable_root=settings.agent_state_root,
            quarantine_root=settings.agent_state_root / "quarantine",
        )
        lifecycle.mark_workspace_prepared(repo_workspace, scrub=True)

        allow_sim = job.model_policy == "fake"
        needs_attest = job.fix_authorization is not None or (
            job.command_intent is not None and job.command_intent.kind == "fix"
        )
        if needs_attest:
            if not lifecycle.ct103_nonce:
                if allow_sim:
                    from agent_workers.executor.lifecycle import issue_ct103_nonce

                    lifecycle.ct103_nonce = issue_ct103_nonce()
                else:
                    raise RuntimeError("missing_ct103_attestation_nonce")
            runtime = resolve_runtime_attestation(
                repo_workspace,
                allow_simulation=allow_sim,
            )
            lifecycle.write_sandbox_attestation(
                run_path,
                runtime_attestation=runtime,
            )
            lifecycle.mark_work_started()

        context_receipt = {
            "schema_version": "context_receipt.v1",
            "run_id": job.run_id,
            "flow": job.flow,
            "agent": job.agent,
            "sources": list(job.context_pack.context_sources) if job.context_pack else [],
            "excluded": [],
            "budget": {"used_context_bytes": 0},
        }
        write_json(run_path / "context_receipt.json", context_receipt)
        if job.context_pack is not None:
            write_json(run_path / "context_pack.json", job.context_pack.model_dump(mode="json"))

        policy_dict = effective.model_dump(mode="json")
        policy_dict["warnings"] = warnings

        engine = get_engine(job.model_policy)
        update_metadata_engine(meta_path, engine.name)
        tool_registry = make_registry(policy_dict, session)
        context_broker = ContextBroker(repo_workspace, profile=job.flow)

        session.emit(SessionEventType.FAKE_ENGINE_STARTED if job.model_policy == "fake" else SessionEventType.MODEL_CALL_STARTED)
        update_metadata_status(meta_path, RunStatus.RUNNING)
        result = engine.run(
            job.model_dump(mode="json"),
            repo_workspace,
            policy_dict,
            artifact_dir=str(run_path),
            context_broker=context_broker,
            tools=tool_registry,
        )
        session.emit(SessionEventType.FAKE_ENGINE_COMPLETED if job.model_policy == "fake" else SessionEventType.MODEL_CALL_COMPLETED)

        context_sources = _context_sources_from_trace(run_path / "rlm_trace.jsonl")
        if context_sources:
            context_receipt["sources"] = context_sources
            context_receipt["budget"]["used_context_bytes"] = sum(len(s) for s in context_sources)
            write_json(run_path / "context_receipt.json", context_receipt)

        trace_path = run_path / "rlm_trace.jsonl"
        runner_trace = json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "run_id": job.run_id,
                "engine": engine.name,
                "event": "runner_metadata",
            }
        )
        if trace_path.is_file():
            existing = trace_path.read_text(encoding="utf-8").rstrip("\n")
            trace_path.write_text(f"{existing}\n{runner_trace}\n", encoding="utf-8")
        else:
            trace_path.write_text(f"{runner_trace}\n", encoding="utf-8")

        result.engine = engine.name
        result.trace_path = str(run_path / "rlm_trace.jsonl")
        result.context_receipt_path = str(run_path / "context_receipt.json")

        if result.fix_result is not None and result.status == "completed":
            write_json(run_path / "fix_result.json", result.fix_result.model_dump(mode="json"))
            binding = job.fix_authorization
            allowed_files = list(binding.allowed_files) if binding is not None else []
            session.emit(SessionEventType.FIX_APPLY_STARTED)
            try:
                raw_patch_rel = apply_fix_to_workspace(
                    repo_workspace,
                    result.fix_result,
                    allowed_files,
                    run_path,
                )
                session.emit(SessionEventType.POST_APPLY_DIFF_ASSERT)
                session.emit(SessionEventType.RAW_PATCH_WRITTEN, artifact=raw_patch_rel)
                session.emit(SessionEventType.DIFF_GATE_STARTED)
                try:
                    gate_result = run_closed_world_diff_gate(
                        repo_root=repo_workspace,
                        policy_workspace=policy_workspace,
                        artifact_root=run_path,
                        job=job.model_dump(mode="json"),
                        fix_ci_hints=list(result.fix_result.ci_hints),
                    )
                    session.emit(SessionEventType.DIFF_GATE_PASSED)
                    result.patch_path = APPROVED_PATCH_NAME
                    result.diff_gate_result = gate_result.model_dump(mode="json")
                    session.emit(SessionEventType.PATCH_ARTIFACT_WRITTEN, artifact=APPROVED_PATCH_NAME)
                    patch_verdict = evaluate_patch_artifact(
                        run_path,
                        repo_workspace,
                        allowed_files,
                    )
                    if not patch_verdict.passed:
                        write_quality_gate_result(run_path, patch_verdict)
                        write_json(
                            run_path / "error.json",
                            {
                                "stage": "patch_quality_gate",
                                "message": "; ".join(patch_verdict.reasons),
                                "allowed_files": allowed_files,
                            },
                        )
                        result.status = "failed"
                        result.terminal_status = TERMINAL_STATUS_FAILED_QUALITY_GATE
                        result.summary = render_fix_quality_failed(
                            run_id=job.run_id,
                            reasons=patch_verdict.reasons,
                            fallback_attempted=False,
                        )
                        session.emit(SessionEventType.FIX_QUALITY_GATE_FAILED, message="patch quality gate failed")
                        session.emit(SessionEventType.FIX_FAILED, message="patch quality gate failed")
                    else:
                        session.emit(SessionEventType.FIX_APPLY_COMPLETED)
                        if lifecycle.sandbox_attestation is None:
                            # Late path: fix result without pre-work attestation
                            if not lifecycle.ct103_nonce:
                                raise RuntimeError("missing_ct103_attestation_nonce")
                            runtime = resolve_runtime_attestation(
                                repo_workspace,
                                allow_simulation=allow_sim,
                            )
                            lifecycle.write_sandbox_attestation(
                                run_path,
                                runtime_attestation=runtime,
                            )
                            lifecycle.mark_work_started()
                        _write_fix_patch_bundle(
                            repo_workspace=repo_workspace,
                            run_path=run_path,
                            job=job,
                            result=result,
                            settings=settings,
                            session=session,
                            gate_result=gate_result,
                            lifecycle=lifecycle,
                        )
                        if result.fix_status is None:
                            result.fix_status = FIX_STATUS_PATCH_BUNDLE_READY
                        if (
                            result.fix_status == FIX_STATUS_PATCH_BUNDLE_READY
                            and result.fix_result is not None
                            and result.summary is None
                        ):
                            result.summary = fit_summary_for_comment(
                                render_fix_comment(
                                    result.fix_result,
                                    patch_artifact=APPROVED_PATCH_NAME,
                                    ci_matrix=gate_result.selected_ci_matrix,
                                ),
                                GITEA_COMMENT_SUMMARY_PROMPT_BUDGET_CHARS,
                            )
                except DiffGateError as gate_exc:
                    gate_result = gate_exc.result
                    result.diff_gate_result = gate_result.model_dump(mode="json")
                    failure_payload = {
                        "stage": "diff_gate",
                        "message": str(gate_exc),
                        "allowed_files": allowed_files,
                        "violations": [v.model_dump(mode="json") for v in gate_result.violations],
                        "violation_codes": gate_result.violation_codes(),
                    }
                    write_json(run_path / "error.json", failure_payload)
                    result.status = "failed"
                    result.terminal_status = TERMINAL_STATUS_FAILED_GATE
                    result.summary = render_fix_gate_failed(
                        run_id=job.run_id,
                        gate_result=gate_result,
                        allowed_files_count=len(allowed_files),
                    )
                    session.emit(SessionEventType.DIFF_GATE_FAILED, message=str(gate_exc))
                    session.emit(SessionEventType.FIX_FAILED, message=str(gate_exc))
            except ApplyFixError as exc:
                failure_payload = {
                    "stage": exc.stage,
                    "message": str(exc),
                    "allowed_files": exc.allowed_files or allowed_files,
                    "changed_files_so_far": exc.changed_files_so_far,
                }
                write_json(run_path / "error.json", failure_payload)
                result.status = "failed"
                result.terminal_status = TERMINAL_STATUS_FAILED_APPLY
                result.summary = render_fix_failed(
                    run_id=job.run_id,
                    stage=exc.stage,
                    message=str(exc),
                    allowed_files_count=len(allowed_files),
                )
                session.emit(SessionEventType.FIX_FAILED, message=str(exc))

        if result.review_result is not None:
            write_json(run_path / "review_result.json", result.review_result.model_dump(mode="json"))
        if result.plan_result is not None:
            write_json(run_path / "plan_result.json", result.plan_result.model_dump(mode="json"))
        if result.terminal_status is None:
            result.terminal_status = (
                TERMINAL_STATUS_COMPLETED
                if result.status == "completed"
                else infer_terminal_status_from_artifacts(run_path, result.status)
            )
        write_json(run_path / "result.json", result.model_dump(mode="json"))
        final_status = RunStatus.COMPLETED if result.status == "completed" else RunStatus.FAILED
        update_metadata_status(meta_path, final_status)

        redaction = RedactionReport(
            run_id=job.run_id,
            rules_loaded=redactor.rules_loaded,
            events_scanned=session.events_scanned,
        )
        write_json(run_path / "redaction_report.json", redaction.model_dump(mode="json"))

        dispatch_report(settings=settings, job=job, run_path=run_path, result=result, session=session)
        session.emit(
            SessionEventType.RUN_COMPLETED if result.status == "completed" else SessionEventType.RUN_FAILED,
            message=result.summary if result.status != "completed" else None,
        )

        return {
            "status": result.status,
            "run_id": job.run_id,
            "artifact_root": str(run_path),
        }

    except Exception as exc:
        return finalize_failed_run(
            job=job,
            run_path=run_path,
            session=session,
            settings=settings,
            exc=exc,
            redactor=redactor,
            meta_path=meta_path,
            traceback_text=traceback.format_exc(),
        )
