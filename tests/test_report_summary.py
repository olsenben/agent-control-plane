"""Report job summary truncation for Gitea comments and inbox events."""

import json
from pathlib import Path

import pytest

from agent_shared.constants import GITEA_COMMENT_SUMMARY_MAX_CHARS
from agent_workers.jobs.report import process_report


@pytest.fixture
def report_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    state = tmp_path / "agent-state"
    state.mkdir()
    run_path = tmp_path / "runs" / "run-test"
    run_path.mkdir(parents=True)
    (run_path / "metadata.json").write_text('{"status": "completed"}', encoding="utf-8")
    monkeypatch.setenv("AGENT_STATE_ROOT", str(state))
    monkeypatch.setenv("AGENT_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    return run_path


def test_inbox_summary_truncated_final_report_full(report_env: Path) -> None:
    long_summary = "s" * 5000
    process_report(
        {
            "run_id": "run-test",
            "project": "ai-sdlc-lab/demo-app",
            "artifact_root": str(report_env),
            "job": {"flow": "inspect", "agent": "explainer", "trigger_context": {}},
            "result": {
                "summary": long_summary,
                "flow": "inspect",
                "agent": "explainer",
                "status": "completed",
                "risk_class": "read_only",
            },
        }
    )
    inbox = json.loads(
        (report_env.parents[1] / "agent-state" / "inbox" / "ct104-results" / "run-test.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(inbox["summary"]) == GITEA_COMMENT_SUMMARY_MAX_CHARS
    report_text = (report_env / "final_report.md").read_text(encoding="utf-8")
    assert long_summary in report_text
