"""Terminal report idempotency tests (Slice 5.1)."""

import json
from pathlib import Path
from unittest.mock import patch

from agent_control.results_ingest import ingest_result_file
from agent_shared.models.jobs import RLMJob
from agent_workers.flows.failure_report import finalize_failed_run, terminal_report_exists
from agent_workers.artifacts.session_events import SessionEventWriter
from agent_workers.security.redactor import SecretRedactor
from agent_workers.settings import WorkerSettings


def test_terminal_report_idempotency(tmp_path: Path) -> None:
    state = tmp_path / "state"
    run_path = tmp_path / "runs" / "ai-sdlc-lab" / "demo" / "run-idem"
    run_path.mkdir(parents=True)
    state.mkdir()
    (run_path / "metadata.json").write_text('{"status":"running"}', encoding="utf-8")
    inbox_dir = state / "inbox" / "ct104-results"
    inbox_dir.mkdir(parents=True)

    settings = WorkerSettings(
        redis_url="redis://localhost:6379/0",
        agent_runs_dir=tmp_path / "runs",
        agent_cache_dir=tmp_path / "cache",
        agent_state_root=state,
        gitea_base_url="http://gitea",
        gitea_agent_token="",
        gitea_bot_token="",
        gitea_agent_comment_enabled=False,
        git_ro_key_path=None,
        model_policy="fake",
        fix_remote_publish_enabled=False,
    )
    job = RLMJob.model_validate(
        {
            "run_id": "run-idem",
            "job_id": "j1",
            "workflow_id": "run-idem",
            "session_id": "run-idem",
            "workflow_definition": "planner/v1",
            "flow_config_id": "planner",
            "flow_version": "0.1.0",
            "flow_config_schema_version": "v1",
            "project": "ai-sdlc-lab/demo",
            "owner": "ai-sdlc-lab",
            "repo": "demo",
            "repo_url": "http://example/repo",
            "primary_branch": "main",
            "policy_ref": "main",
            "base_ref": "main",
            "target_sha": None,
            "task_ref": "main",
            "proposed_agent_branch": "agent/run-idem",
            "trigger_event_id": "t1",
            "trigger_delivery_id": None,
            "trigger_type": "manual",
            "trigger_context": {"event_type": "manual"},
            "flow": "planner",
            "agent": "planner",
            "risk_class": "planning_only",
            "command_intent": {"kind": "plan", "natural_language_task": "x"},
            "reporting": {},
            "limits": {},
            "safety": {},
            "model_policy": "fake",
            "state_path": str(state / "v.json"),
        }
    )
    session = SessionEventWriter(run_path / "session_events.jsonl", job.run_id, SecretRedactor())

    with patch("agent_workers.flows.failure_report.enqueue_report"):
        finalize_failed_run(
            job=job,
            run_path=run_path,
            session=session,
            settings=settings,
            exc=RuntimeError("boom"),
            redactor=SecretRedactor(),
            meta_path=run_path / "metadata.json",
        )

    inbox = inbox_dir / "run-idem.json"
    assert not inbox.is_file()  # enqueue_report mocked

    inbox.write_text(
        json.dumps(
            {
                "schema_version": "agent_run_completed.v1",
                "run_id": "run-idem",
                "job_id": "j1",
                "workflow_id": "run-idem",
                "session_id": "run-idem",
                "trigger_event_id": "t1",
                "project": "ai-sdlc-lab/demo",
                "flow": "planner",
                "agent": "planner",
                "risk_class": "planning_only",
                "status": "failed",
                "terminal_status": "failed_infra",
                "summary": "failed",
                "artifact_root": str(run_path),
            }
        ),
        encoding="utf-8",
    )
    assert terminal_report_exists(run_path, state, "run-idem")

    payload_text = inbox.read_text(encoding="utf-8")
    stored1, created1 = ingest_result_file(state, inbox)
    assert created1 is True
    inbox.write_text(payload_text, encoding="utf-8")
    stored2, created2 = ingest_result_file(state, inbox)
    assert created1 is True
    assert created2 is False
    assert stored1 == stored2
