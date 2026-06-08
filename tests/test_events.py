import json
from pathlib import Path

from agent_control.events import (
    AgentEvent,
    append_event,
    deterministic_event_id,
    load_project_events,
    reduction_outbox_path,
    write_reduction_outbox,
    write_verification_state,
)
from agent_control.state_reducer import LogicalState


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
    p1, created1 = append_event(tmp_path, event)
    p2, created2 = append_event(tmp_path, event)
    assert p1 == p2
    assert created1 is True
    assert created2 is False
    data = json.loads(p1.read_text(encoding="utf-8"))
    assert data["event_id"] == "evt001"
    assert data["schema"] == "agent.event.v1"


def test_load_project_events_stable_sort(tmp_path: Path) -> None:
    project = "ai-sdlc-lab/demo-app"
    e1 = AgentEvent(
        event_id="aaa",
        type="gitea.push",
        project=project,
        recorded_at="2026-06-05T10:00:00+00:00",
        payload={},
    )
    e2 = AgentEvent(
        event_id="bbb",
        type="gitea.issue_comment",
        project=project,
        recorded_at="2026-06-05T10:00:00+00:00",
        payload={},
    )
    append_event(tmp_path, e1)
    append_event(tmp_path, e2)
    loaded = load_project_events(tmp_path, project)
    assert [item["event_id"] for item in loaded] == ["aaa", "bbb"]


def test_write_verification_state_atomic(tmp_path: Path) -> None:
    state = LogicalState(project="ai-sdlc-lab/demo-app", event_count=1)
    path = write_verification_state(tmp_path, "ai-sdlc-lab/demo-app", state)
    assert path.name == "verification_state.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["event_count"] == 1


def test_reduction_outbox(tmp_path: Path) -> None:
    path = write_reduction_outbox(tmp_path, "evt-1", "ai-sdlc-lab/demo-app")
    assert path == reduction_outbox_path(tmp_path, "evt-1")
    marker = json.loads(path.read_text(encoding="utf-8"))
    assert marker["event_id"] == "evt-1"
