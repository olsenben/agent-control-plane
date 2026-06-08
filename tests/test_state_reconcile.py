import json
from pathlib import Path

from click.testing import CliRunner

from agent_control.cli import main
from agent_control.events import write_reduction_outbox


def test_state_reconcile_processes_outbox(tmp_path: Path, monkeypatch) -> None:
    project = "ai-sdlc-lab/agent-control-plane"
    monkeypatch.setenv("AGENT_STATE_ROOT", str(tmp_path))
    write_reduction_outbox(tmp_path, "evt-outbox", project)

    runner = CliRunner()
    result = runner.invoke(main, ["state", "reconcile", "--project", project])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert len(payload["reconciled"]) == 1
    assert payload["reconciled"][0]["project"] == project
