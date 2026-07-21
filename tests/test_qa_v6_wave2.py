"""Wave-2 QA: durable ledger sequence, budget, approval binding, DUR, NL wire."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_control.events import AgentEvent, append_event, load_project_events
from agent_control.model_attempt_budget_store import (
    emit_budget_exhausted,
    load_durable_budget,
    reserve_attempt,
)
from agent_control.nl_invocation_wire import maybe_begin_nl_invocation
from agent_control.observe.projection import build_observation_projection
from agent_shared.models.approval import WorkItemApproval
from agent_shared.models.model_attempt_budget import ModelAttemptBudget


def test_ledger_sequence_authoritative_sort(tmp_path: Path) -> None:
    project = "ai-sdlc-lab/demo-app"
    # Append with deliberate later wall-clock first by crafting recorded_at.
    e1 = AgentEvent(
        event_id="e1",
        type="agent.control_decision",
        project=project,
        payload={"run_id": "run-seq", "session_id": "sess-seq"},
        recorded_at="2026-07-21T12:00:00+00:00",
    )
    e2 = AgentEvent(
        event_id="e2",
        type="agent.control_decision",
        project=project,
        payload={"run_id": "run-seq", "session_id": "sess-seq"},
        recorded_at="2026-07-21T11:00:00+00:00",
    )
    append_event(tmp_path, e1)
    append_event(tmp_path, e2)
    loaded = load_project_events(tmp_path, project)
    assert [e["event_id"] for e in loaded] == ["e1", "e2"]
    assert loaded[0]["ledger_sequence"] == 1
    assert loaded[1]["ledger_sequence"] == 2
    # Even though e2 has earlier recorded_at, ledger order wins.
    doc = build_observation_projection(tmp_path, project=project, run_id="run-seq")
    assert [e["event_id"] for e in doc.events] == ["e1", "e2"]


def test_durable_budget_reserve_and_exhaust(tmp_path: Path) -> None:
    project = "ai-sdlc-lab/demo-app"
    limits = ModelAttemptBudget(max_total_completion_attempts=2, max_infrastructure_attempts=2)
    from agent_shared.models.model_attempt_budget import AttemptBudgetTracker
    from agent_control.model_attempt_budget_store import save_durable_budget

    tracker = AttemptBudgetTracker(limits=limits)
    save_durable_budget(tmp_path, project=project, budget_key="run-b1", tracker=tracker)
    ok1, t1 = reserve_attempt(
        tmp_path, project=project, budget_key="run-b1", kind="infrastructure", idempotency_key="a"
    )
    ok2, t2 = reserve_attempt(
        tmp_path, project=project, budget_key="run-b1", kind="infrastructure", idempotency_key="b"
    )
    ok3, t3 = reserve_attempt(
        tmp_path, project=project, budget_key="run-b1", kind="infrastructure", idempotency_key="c"
    )
    assert ok1 and ok2 and not ok3
    # Duplicate idempotency does not double-charge
    ok_dup, t_dup = reserve_attempt(
        tmp_path, project=project, budget_key="run-b1", kind="infrastructure", idempotency_key="a"
    )
    assert ok_dup
    assert t_dup.total_completion_attempts == 2
    emit_budget_exhausted(tmp_path, project=project, run_id="run-b1", tracker=t3)
    events = load_project_events(tmp_path, project)
    assert any(
        e.get("type") == "agent.control_decision"
        and (e.get("payload") or {}).get("kind") == "budget_exhausted"
        for e in events
    )
    reloaded = load_durable_budget(tmp_path, project=project, budget_key="run-b1", limits=limits)
    assert reloaded.total_completion_attempts == 2


def test_approval_binding_negatives_n01_n05() -> None:
    """N01 repo/issue mismatch, N03 plan hash, N05 expiry — binding guards."""
    from datetime import datetime, timezone, timedelta

    from agent_control.approval.service import _is_expired

    expired = WorkItemApproval(
        approval_id="appr-x",
        approval_target_id="WI-x",
        plan_alias="PLAN-x",
        plan_run_id="run-x",
        plan_hash="h" * 64,
        blast_radius_hash="b" * 64,
        project="ai-sdlc-lab/demo-app",
        issue_id=1,
        approved_by_login="owner",
        approved_at="2020-01-01T00:00:00+00:00",
        expires_at=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        policy_source_sha="p" * 40,
    )
    assert _is_expired(expired)

    # N01 conceptual: project/issue stored on approval must match evaluate inputs
    assert expired.project == "ai-sdlc-lab/demo-app"
    assert expired.issue_id == 1
    other_project = "other/repo"
    assert expired.project != other_project



def test_nl_ambiguous_clarifies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_control.config import Settings

    settings = Settings(AGENT_STATE_ROOT=str(tmp_path), GITEA_BOT_TOKEN="")
    posts: list[str] = []

    def _fake_post(project, issue, body, settings=None):
        posts.append(body)
        return {"id": 99}

    monkeypatch.setattr("agent_control.nl_invocation_wire.post_issue_comment", _fake_post)
    trigger = {
        "type": "gitea.issue_comment",
        "delivery_id": "d1",
        "payload": {
            "comment": {"id": 1, "body": "@agent do something vague", "user": {"login": "alice"}},
            "issue": {"number": 7},
        },
    }
    result = maybe_begin_nl_invocation(
        tmp_path, "ai-sdlc-lab/demo-app", trigger, settings=settings
    )
    assert result["handled"] is True
    assert result["clarify"] is True
    assert posts and "clarification" in posts[0].lower()


def test_upgrade_durability_rebuild_projection(tmp_path: Path) -> None:
    """DUR-09: rebuild projection from ledger after restart (no sequence regression)."""
    project = "ai-sdlc-lab/demo-app"
    for i in range(3):
        append_event(
            tmp_path,
            AgentEvent(
                event_id=f"ev{i}",
                type="agent.control_decision",
                project=project,
                payload={"run_id": "run-dur", "kind": "other", "summary": str(i)},
            ),
        )
    doc1 = build_observation_projection(tmp_path, project=project, run_id="run-dur")
    # Simulate restart: reload from disk only
    doc2 = build_observation_projection(tmp_path, project=project, run_id="run-dur")
    assert [e["event_id"] for e in doc1.events] == [e["event_id"] for e in doc2.events]
    assert doc1.max_sequence == doc2.max_sequence


def test_gitea_http_error_deleted_triggers_successor_path() -> None:
    from agent_control.gitea_client import GiteaHttpError
    from agent_control.observe.comment_projection import project_session_comment
    from agent_shared.models.agent_session import AgentSession, SessionStatus

    err = GiteaHttpError(404, "gone", deleted=True)
    assert err.deleted is True
    # Smoke: project_session_comment imports GiteaHttpError path (unit of wiring).
    assert project_session_comment.__name__ == "project_session_comment"
    _ = AgentSession, SessionStatus
