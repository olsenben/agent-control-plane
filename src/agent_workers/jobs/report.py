"""Report queue job: final report and CT103 result intake."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from agent_shared.constants import RunStatus, SessionEventType
from agent_shared.models.events import AgentRunCompletedEvent
from agent_workers.artifacts.session_events import SessionEventWriter
from agent_workers.artifacts.writer import update_metadata_status, write_json
from agent_workers.gitea_reporter import maybe_post_comment
from agent_workers.security.redactor import SecretRedactor
from agent_workers.settings import get_worker_settings


def process_report(job_payload: dict[str, Any]) -> dict[str, Any]:
    settings = get_worker_settings()
    run_id = job_payload["run_id"]
    project = job_payload["project"]
    artifact_root = Path(job_payload["artifact_root"])
    job = job_payload.get("job", {})
    result = job_payload.get("result", {})

    session_path = artifact_root / "session_events.jsonl"
    session = SessionEventWriter(session_path, run_id, SecretRedactor())
    session.emit(SessionEventType.REPORT_STARTED)
    update_metadata_status(artifact_root / "metadata.json", RunStatus.REPORTING)

    summary = result.get("summary", "Run completed.")
    report_body = (
        f"# Agent run report\n\n"
        f"- run_id: `{run_id}`\n"
        f"- project: `{project}`\n"
        f"- flow: `{result.get('flow', job.get('flow'))}`\n"
        f"- status: `{result.get('status')}`\n"
        f"- risk_class: `{result.get('risk_class', job.get('risk_class'))}`\n\n"
        f"## Summary\n\n{summary}\n\n"
        f"Artifacts: `{artifact_root}`\n"
    )
    redactor = SecretRedactor()
    report_body, _ = redactor.redact_text(report_body)
    (artifact_root / "final_report.md").write_text(report_body, encoding="utf-8")

    completed = AgentRunCompletedEvent(
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
        status=result.get("status", "completed"),
        summary=summary[:500],
        artifact_root=str(artifact_root),
    )

    events_dir = artifact_root / "events"
    events_dir.mkdir(exist_ok=True)
    event_path = events_dir / "agent_run_completed.json"
    write_json(event_path, completed.model_dump(mode="json"))

    inbox_dir = settings.agent_state_root / "inbox" / "ct104-results"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    inbox_path = inbox_dir / f"{run_id}.json"
    tmp = inbox_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(completed.model_dump(mode="json"), indent=2), encoding="utf-8")
    os.replace(tmp, inbox_path)

    comment_result = maybe_post_comment(settings, job, completed, artifact_root)
    session.emit(SessionEventType.REPORT_COMPLETED, message=comment_result.get("status", "ok"))
    update_metadata_status(artifact_root / "metadata.json", RunStatus.REPORTED)

    return {
        "status": "reported",
        "run_id": run_id,
        "inbox_path": str(inbox_path),
        "comment": comment_result,
    }
