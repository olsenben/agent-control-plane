"""RQ exception handler for rlm-root jobs (Slice 5.1 belt-and-suspenders)."""

from __future__ import annotations

from pathlib import Path

from agent_shared.models.jobs import RLMJob
from agent_workers.flows.failure_report import (
    finalize_failed_run,
    terminal_report_exists,
)
from agent_workers.settings import get_worker_settings


def handle_rlm_job_exception(job, exc_type, exc_value, traceback_obj) -> bool:
    """Return False to suppress FailedJobRegistry when terminal report was written."""
    args = job.args or ()
    if not args:
        return True
    job_payload = args[0]
    if not isinstance(job_payload, dict):
        return True

    settings = get_worker_settings()
    try:
        rlm_job = RLMJob.model_validate(job_payload)
    except Exception:
        return True

    run_path = Path(settings.agent_runs_dir) / rlm_job.project / rlm_job.run_id
    if terminal_report_exists(run_path, settings.agent_state_root, rlm_job.run_id):
        return False

    if not run_path.is_dir():
        return True

    from agent_workers.artifacts.session_events import SessionEventWriter
    from agent_workers.security.redactor import SecretRedactor

    session = SessionEventWriter(run_path / "session_events.jsonl", rlm_job.run_id, SecretRedactor())
    meta_path = run_path / "metadata.json"
    exc = exc_value if isinstance(exc_value, BaseException) else Exception(str(exc_value))
    try:
        finalize_failed_run(
            job=rlm_job,
            run_path=run_path,
            session=session,
            settings=settings,
            exc=exc,
            redactor=SecretRedactor(),
            meta_path=meta_path,
        )
    except Exception:
        return True
    return False
