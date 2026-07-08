"""Terminal failure reporting helpers (Slice 5.1)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_control.queue import enqueue_report
from agent_shared.constants import (
    TERMINAL_STATUS_COMPLETED,
    TERMINAL_STATUS_FAILED_APPLY,
    TERMINAL_STATUS_FAILED_GATE,
    TERMINAL_STATUS_FAILED_INFRA,
    TERMINAL_STATUS_FAILED_PARSE,
    TERMINAL_STATUS_FAILED_PUBLISH,
    TERMINAL_STATUS_FAILED_PUBLISH_PARTIAL,
    TERMINAL_STATUS_FAILED_PUBLISH_PRECHECK,
    TERMINAL_STATUS_FAILED_QUALITY_GATE,
)
from agent_shared.models.jobs import RLMJob
from agent_shared.models.runs import AgentError, RLMResult
from agent_shared.models.session import RedactionReport
from agent_shared.constants import RunStatus, SessionEventType
from agent_workers.artifacts.errors import write_error
from agent_workers.artifacts.session_events import SessionEventWriter
from agent_workers.artifacts.writer import update_metadata_status, write_json
from agent_workers.security.redactor import SecretRedactor
from agent_workers.settings import WorkerSettings


def _stage_terminal_status(stage: str) -> str | None:
    if stage in ("quality_gate", "patch_quality_gate"):
        return TERMINAL_STATUS_FAILED_QUALITY_GATE
    if stage in ("publish_preflight",):
        return TERMINAL_STATUS_FAILED_PUBLISH_PRECHECK
    if stage in ("diff_gate", "pre_push_gate"):
        return TERMINAL_STATUS_FAILED_GATE
    if stage in ("stale_approval_base", "branch_push", "pr_open"):
        return TERMINAL_STATUS_FAILED_PUBLISH
    if stage == "publish_partial":
        return TERMINAL_STATUS_FAILED_PUBLISH_PARTIAL
    if stage:
        return TERMINAL_STATUS_FAILED_APPLY
    return None


def classify_terminal_status(run_path: Path, exc: Exception) -> str:
    if (run_path / "parse_failure.json").exists():
        return TERMINAL_STATUS_FAILED_PARSE
    message = str(exc).lower()
    if "failed to parse" in message:
        return TERMINAL_STATUS_FAILED_PARSE
    error_path = run_path / "error.json"
    if error_path.is_file():
        try:
            data = json.loads(error_path.read_text(encoding="utf-8"))
            mapped = _stage_terminal_status(str(data.get("stage", "")))
            if mapped:
                return mapped
        except (json.JSONDecodeError, OSError, TypeError):
            pass
    return TERMINAL_STATUS_FAILED_INFRA


def infer_terminal_status_from_artifacts(run_path: Path, result_status: str) -> str:
    if result_status == "completed":
        return TERMINAL_STATUS_COMPLETED
    if (run_path / "quality_gate_result.json").exists():
        try:
            qg = json.loads((run_path / "quality_gate_result.json").read_text(encoding="utf-8"))
            if not qg.get("passed"):
                stage = str(qg.get("stage") or "")
                if stage == "publish_preflight":
                    return TERMINAL_STATUS_FAILED_PUBLISH_PRECHECK
                return TERMINAL_STATUS_FAILED_QUALITY_GATE
        except (json.JSONDecodeError, OSError, TypeError):
            pass
    if (run_path / "parse_failure.json").exists():
        return TERMINAL_STATUS_FAILED_PARSE
    error_path = run_path / "error.json"
    if error_path.is_file():
        try:
            data = json.loads(error_path.read_text(encoding="utf-8"))
            mapped = _stage_terminal_status(str(data.get("stage", "")))
            if mapped:
                return mapped
        except (json.JSONDecodeError, OSError, TypeError):
            pass
    publish_path = run_path / "remote_publish_result.json"
    if publish_path.is_file():
        try:
            pub = json.loads(publish_path.read_text(encoding="utf-8"))
            if pub.get("publish_state") == "publish_failed_partial":
                return TERMINAL_STATUS_FAILED_PUBLISH_PARTIAL
        except (json.JSONDecodeError, OSError, TypeError):
            pass
    return TERMINAL_STATUS_FAILED_INFRA


def build_failure_summary(run_id: str, terminal_status: str, message: str) -> str:
    label = terminal_status.replace("_", " ")
    excerpt = message.strip()[:500]
    return f"Agent run `{run_id}` failed ({label}).\n\n{excerpt}"


def build_failed_rlm_result(job: RLMJob, message: str, terminal_status: str) -> RLMResult:
    return RLMResult(
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
        terminal_status=terminal_status,
        summary=build_failure_summary(job.run_id, terminal_status, message),
    )


def publish_resume_allowed(run_path: Path) -> bool:
    publish_path = run_path / "remote_publish_result.json"
    if not publish_path.is_file():
        return False
    try:
        pub = json.loads(publish_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    return pub.get("publish_state") in ("publish_failed_partial", "branch_published")


def terminal_report_exists(run_path: Path, state_root: Path, run_id: str) -> bool:
    if publish_resume_allowed(run_path):
        return False
    inbox = state_root / "inbox" / "ct104-results" / f"{run_id}.json"
    return (run_path / "result.json").is_file() and inbox.is_file()


def dispatch_report(
    *,
    settings: WorkerSettings,
    job: RLMJob,
    run_path: Path,
    result: RLMResult,
    session: SessionEventWriter,
) -> None:
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


def finalize_failed_run(
    *,
    job: RLMJob,
    run_path: Path,
    session: SessionEventWriter,
    settings: WorkerSettings,
    exc: Exception,
    redactor: SecretRedactor,
    meta_path: Path,
    traceback_text: str | None = None,
) -> dict[str, Any]:
    terminal_status = classify_terminal_status(run_path, exc)
    err = AgentError(
        run_id=job.run_id,
        stage="rlm_root",
        error_type=type(exc).__name__,
        message=str(exc),
        recoverable=False,
        details={
            "traceback": traceback_text or "",
            "terminal_status": terminal_status,
        },
    )
    write_error(run_path / "error.json", err)
    failed = build_failed_rlm_result(job, str(exc), terminal_status)
    write_json(run_path / "result.json", failed.model_dump(mode="json"))
    update_metadata_status(meta_path, RunStatus.FAILED)
    redaction = RedactionReport(
        run_id=job.run_id,
        rules_loaded=redactor.rules_loaded,
        events_scanned=session.events_scanned,
    )
    write_json(run_path / "redaction_report.json", redaction.model_dump(mode="json"))
    dispatch_report(settings=settings, job=job, run_path=run_path, result=failed, session=session)
    session.emit(SessionEventType.RUN_FAILED, message=failed.summary)
    return {
        "status": "failed",
        "run_id": job.run_id,
        "artifact_root": str(run_path),
        "terminal_status": terminal_status,
    }
