"""CT104 flow session runner — deterministic job lifecycle."""

from __future__ import annotations

import json
import traceback
from datetime import datetime, timezone
from typing import Any

from agent_control.queue import enqueue_report
from agent_shared.constants import RunStatus, SessionEventType
from agent_shared.models.jobs import RLMJob
from agent_shared.models.runs import AgentError, RLMResult
from agent_shared.models.session import BootstrapInfo, RedactionReport, SystemContext
from agent_workers.artifacts.errors import write_error
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
from agent_workers.repo.policy_loader import clone_repo, load_policy, write_policy_artifacts
from agent_workers.rlm.engine import get_engine
from agent_workers.runtime.capabilities import detect_capabilities, python_version
from agent_workers.security.redactor import SecretRedactor
from agent_workers.settings import WorkerSettings, get_worker_settings
from agent_workers.tools.registry import make_registry


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
        try:
            clone_repo(settings, job.repo_url, job.policy_ref, policy_workspace)
            clone_repo(settings, job.repo_url, job.task_ref, repo_workspace)
        except Exception:
            repo_workspace.mkdir(parents=True, exist_ok=True)
            policy_workspace = repo_workspace

        bootstrap = BootstrapInfo(
            run_id=job.run_id,
            worker="worker-rlm-root",
            queue="rlm-root",
            repo_url=job.repo_url,
            checkout_ref=job.task_ref,
            policy_ref=job.policy_ref,
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

        context_receipt = {
            "schema_version": "context_receipt.v1",
            "run_id": job.run_id,
            "flow": job.flow,
            "agent": job.agent,
            "sources": [],
            "excluded": [],
            "budget": {"used_context_bytes": 0},
        }
        write_json(run_path / "context_receipt.json", context_receipt)

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

        trace_lines = [
            json.dumps(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "run_id": job.run_id,
                    "engine": engine.name,
                }
            ),
        ]
        (run_path / "rlm_trace.jsonl").write_text("\n".join(trace_lines) + "\n", encoding="utf-8")

        result.engine = engine.name
        result.trace_path = str(run_path / "rlm_trace.jsonl")
        result.context_receipt_path = str(run_path / "context_receipt.json")
        write_json(run_path / "result.json", result.model_dump(mode="json"))
        update_metadata_status(meta_path, RunStatus.COMPLETED)

        redaction = RedactionReport(
            run_id=job.run_id,
            rules_loaded=redactor.rules_loaded,
            events_scanned=session.events_scanned,
        )
        write_json(run_path / "redaction_report.json", redaction.model_dump(mode="json"))

        report_payload = {
            "run_id": job.run_id,
            "project": job.project,
            "artifact_root": str(run_path),
            "job": job.model_dump(mode="json"),
            "result": result.model_dump(mode="json"),
        }
        try:
            enqueue_report(settings.redis_url, job.run_id, report_payload)
        except Exception:
            from agent_workers.jobs.report import process_report

            process_report(report_payload)
        session.emit(SessionEventType.RUN_COMPLETED)

        return {"status": "completed", "run_id": job.run_id, "artifact_root": str(run_path)}

    except Exception as exc:
        err = AgentError(
            run_id=job.run_id,
            stage="rlm_root",
            error_type=type(exc).__name__,
            message=str(exc),
            recoverable=False,
            details={"traceback": traceback.format_exc()},
        )
        write_error(run_path / "error.json", err)
        failed = RLMResult(
            run_id=job.run_id,
            session_id=job.session_id,
            project=job.project,
            flow=job.flow,
            agent=job.agent,
            risk_class=job.risk_class,
            workflow_definition=job.workflow_definition,
            flow_config_id=job.flow_config_id,
            flow_version=job.flow_version,
            status="failed",
            summary=str(exc),
        )
        write_json(run_path / "result.json", failed.model_dump(mode="json"))
        session.emit(SessionEventType.RUN_FAILED, message=str(exc))
        raise
