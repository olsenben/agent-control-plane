"""Trace metadata append tests."""

import json
from pathlib import Path

from agent_workers.rlm.official_engine import append_trace_event


def test_trace_metadata_appends(tmp_path: Path) -> None:
    trace_path = tmp_path / "rlm_trace.jsonl"
    trace_path.write_text(
        json.dumps({"event": "context_gathered", "sources": ["README.md"]}) + "\n",
        encoding="utf-8",
    )
    append_trace_event(str(tmp_path), {"event": "final_prompt", "provider": "ollama"})
    lines = trace_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["event"] == "context_gathered"
    assert json.loads(lines[1])["event"] == "final_prompt"
