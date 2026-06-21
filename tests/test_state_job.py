import json
from pathlib import Path

import pytest

from agent_control.events import AgentEvent, append_event
from agent_control.jobs.state import process_state_reduction


def _append_comment(tmp_path: Path, body: str, event_id: str, recorded_at: str) -> None:
    event = AgentEvent(
        event_id=event_id,
        type="gitea.issue_comment",
        raw_event_type="issue_comment",
        raw_action="created",
        project="ai-sdlc-lab/agent-control-plane",
        recorded_at=recorded_at,
        payload={
            "action": "created",
            "comment": {"body": body},
            "issue": {"number": 1},
            "repository": {"full_name": "ai-sdlc-lab/agent-control-plane"},
        },
    )
    append_event(tmp_path, event)


def test_process_state_reduction_writes_verification_state(tmp_path: Path) -> None:
    _append_comment(tmp_path, "/agent review the change", "evt-1", "2026-06-05T23:42:07+00:00")
    result = process_state_reduction(str(tmp_path), "evt-1", "ai-sdlc-lab/agent-control-plane")
    state_path = Path(result["state_path"])
    assert state_path.exists()
    data = json.loads(state_path.read_text(encoding="utf-8"))
    assert data["command_intent"]["kind"] == "review"
    assert data["event_count"] == 1
    assert data["last_event_id"] == "evt-1"
    assert result["events_loaded"] == 1


def test_process_state_reduction_idempotent_stable_fields(tmp_path: Path) -> None:
    _append_comment(tmp_path, "test", "evt-1", "2026-06-05T23:42:07+00:00")
    process_state_reduction(str(tmp_path), "evt-1", "ai-sdlc-lab/agent-control-plane")
    process_state_reduction(str(tmp_path), "evt-1", "ai-sdlc-lab/agent-control-plane")
    state_path = tmp_path / "projects/ai-sdlc-lab/agent-control-plane/summaries/verification_state.json"
    data = json.loads(state_path.read_text(encoding="utf-8"))
    assert data["event_count"] == 1
    assert data["last_event_id"] == "evt-1"


def test_bot_completion_comment_preserves_last_command_intent(tmp_path: Path) -> None:
    _append_comment(tmp_path, "/agent review", "evt-review", "2026-06-17T21:13:05+00:00")
    _append_comment(
        tmp_path,
        "@olsenben Agent run `run-abc` **completed** (code_review/reviewer).\n\n## Agent Review",
        "evt-bot",
        "2026-06-17T21:13:36+00:00",
    )
    process_state_reduction(str(tmp_path), "evt-bot", "ai-sdlc-lab/agent-control-plane")
    state_path = tmp_path / "projects/ai-sdlc-lab/agent-control-plane/summaries/verification_state.json"
    data = json.loads(state_path.read_text(encoding="utf-8"))
    assert data["command_intent"]["kind"] == "review"
    assert data["dispatch_recommended"] is False


def test_process_state_reduction_dispatches_from_trigger_when_bot_is_later(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _append_comment(tmp_path, "/agent review", "evt-review", "2026-06-17T21:13:05+00:00")
    _append_comment(
        tmp_path,
        "@olsenben Agent run `run-abc` **completed** (code_review/reviewer).\n\n## Agent Review",
        "evt-bot",
        "2026-06-17T21:13:36+00:00",
    )
    calls: list[str] = []

    def _fake_dispatch(state, trigger, redis_url, settings=None):
        calls.append(trigger["event_id"])
        return {"dispatched": True, "job_id": "rlm-root-test", "run_id": "run-test"}

    monkeypatch.setattr(
        "agent_control.jobs.state.maybe_dispatch_rlm_root",
        _fake_dispatch,
    )

    review_result = process_state_reduction(
        str(tmp_path), "evt-review", "ai-sdlc-lab/agent-control-plane"
    )
    bot_result = process_state_reduction(
        str(tmp_path), "evt-bot", "ai-sdlc-lab/agent-control-plane"
    )

    assert review_result["dispatch"]["dispatched"] is True
    assert bot_result["dispatch"]["dispatched"] is False
    assert calls == ["evt-review"]
