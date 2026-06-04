import json
from pathlib import Path

from agent_control.events import AgentEvent, append_event, deterministic_event_id


def test_deterministic_event_id() -> None:
    a = deterministic_event_id("gitea", "delivery-1", "gitea.push")
    b = deterministic_event_id("gitea", "delivery-1", "gitea.push")
    c = deterministic_event_id("gitea", "delivery-2", "gitea.push")
    assert a == b
    assert a != c


def test_append_event_dedupe(tmp_path: Path) -> None:
    event = AgentEvent(
        event_id="evt001",
        type="gitea.push",
        project="ai-sdlc-lab/demo-app",
        payload={"ref": "refs/heads/main"},
    )
    p1 = append_event(tmp_path, event)
    p2 = append_event(tmp_path, event)
    assert p1 == p2
    data = json.loads(p1.read_text(encoding="utf-8"))
    assert data["event_id"] == "evt001"
    assert data["schema"] == "agent.event.v1"
