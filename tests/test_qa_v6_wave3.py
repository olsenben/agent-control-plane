"""Wave-3 QA: DUR matrix, PATCH reconcile, approval N01–N08, Observatory auth."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agent_control.approval.plan_lookup import PlanRunRecord
from agent_control.approval.service import evaluate_fix_request
from agent_control.events import AgentEvent, append_event, load_project_events
from agent_control.gitea_client import GiteaHttpError
from agent_control.model_attempt_budget_store import reserve_attempt, save_durable_budget
from agent_control.observe.auth import require_observe_repo_read
from agent_control.observe.comment_projection import (
    _reconcile_patch_applied,
    project_session_comment,
)
from agent_control.observe.projection import build_observation_projection
from agent_control.session.storage import persist_session_with_run_index
from agent_shared.models.agent_session import AgentSession, SessionStatus
from agent_shared.models.approval import WorkItemApproval
from agent_shared.models.model_attempt_budget import AttemptBudgetTracker, ModelAttemptBudget


def _approval(**kwargs) -> WorkItemApproval:
    base = dict(
        approval_id="appr-1",
        approval_target_id="WI-0001",
        plan_alias="PLAN-run-1",
        plan_run_id="run-plan-1",
        plan_hash="a" * 64,
        blast_radius_hash="b" * 64,
        project="ai-sdlc-lab/demo-app",
        issue_id=9,
        allowed_files=["README.md"],
        approved_by_login="owner",
        approved_at="2026-07-21T00:00:00+00:00",
        expires_at="2099-01-01T00:00:00+00:00",
        status="approved",
        approved_base_sha="deadbeef",
        approved_base_ref="main",
        policy_source_sha="c" * 40,
    )
    base.update(kwargs)
    return WorkItemApproval(**base)


def _plan(**kwargs) -> PlanRunRecord:
    from agent_shared.models.plan import PlanResult

    plan = PlanResult.model_validate(
        {
            "schema_version": "plan_result.v1",
            "scope_summary": "demo",
            "steps": [],
            "ci_hints": [],
            "blast_radius": {
                "repos": [],
                "services": [],
                "tests": [],
                "adrs": [],
                "missing_edges": [],
            },
            "fixable": True,
        }
    )
    base = dict(
        run_id="run-plan-1",
        project="ai-sdlc-lab/demo-app",
        issue_id=9,
        approval_target_id="WI-0001",
        plan_alias="PLAN-run-1",
        plan_hash="a" * 64,
        blast_radius_hash="b" * 64,
        allowed_files=["README.md"],
        plan_result=plan,
    )
    base.update(kwargs)
    return PlanRunRecord(**base)


def test_n01_reuse_across_repos_denied(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "agent_control.approval.service.resolve_plan_for_target",
        lambda *a, **k: _plan(project="other/repo"),
    )
    monkeypatch.setattr(
        "agent_control.approval.service.load_approval",
        lambda *a, **k: _approval(project="ai-sdlc-lab/demo-app"),
    )
    ev = evaluate_fix_request(tmp_path, project="other/repo", issue_id=9, target="WI-0001")
    assert ev.policy_decision == "blocked"
    assert "mismatch" in (ev.reason or "").lower()


def test_n02_wrong_wi_target_denied(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "agent_control.approval.service.resolve_plan_for_target",
        lambda *a, **k: _plan(approval_target_id="WI-OTHER"),
    )
    monkeypatch.setattr(
        "agent_control.approval.service.load_approval",
        lambda *a, **k: _approval(approval_target_id="WI-0001"),
    )
    # load_approval keyed by resolved plan's target — simulate missing for wrong WI
    monkeypatch.setattr(
        "agent_control.approval.service.load_approval",
        lambda *a, **k: None,
    )
    ev = evaluate_fix_request(tmp_path, project="ai-sdlc-lab/demo-app", issue_id=9, target="WI-OTHER")
    assert ev.policy_decision == "blocked"


def test_n03_plan_hash_mutation_denied(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "agent_control.approval.service.resolve_plan_for_target",
        lambda *a, **k: _plan(plan_hash="d" * 64),
    )
    monkeypatch.setattr(
        "agent_control.approval.service.load_approval",
        lambda *a, **k: _approval(plan_hash="a" * 64),
    )
    ev = evaluate_fix_request(tmp_path, project="ai-sdlc-lab/demo-app", issue_id=9, target="WI-0001")
    assert ev.policy_decision == "blocked"
    assert "plan hash" in (ev.reason or "").lower()


def test_n04_base_sha_force_push_denied(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "agent_control.approval.service.resolve_plan_for_target",
        lambda *a, **k: _plan(),
    )
    monkeypatch.setattr(
        "agent_control.approval.service.load_approval",
        lambda *a, **k: _approval(approved_base_sha="deadbeef"),
    )
    # Skip policy pin network
    monkeypatch.setattr(
        "agent_control.project_registry.resolve_policy_source_pin",
        lambda *a, **k: MagicMock(policy_source_sha="c" * 40),
    )
    monkeypatch.setattr(
        "agent_control.memory.governance.memory_as_governance_check",
        lambda *a, **k: MagicMock(policy_decision="allow"),
    )
    ev = evaluate_fix_request(
        tmp_path,
        project="ai-sdlc-lab/demo-app",
        issue_id=9,
        target="WI-0001",
        expected_base_sha="cafebabe",
    )
    assert ev.policy_decision == "blocked"
    assert "base sha" in (ev.reason or "").lower()


def test_n05_expired_approval_denied(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    expired_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    monkeypatch.setattr(
        "agent_control.approval.service.resolve_plan_for_target",
        lambda *a, **k: _plan(),
    )
    monkeypatch.setattr(
        "agent_control.approval.service.load_approval",
        lambda *a, **k: _approval(expires_at=expired_at),
    )
    ev = evaluate_fix_request(tmp_path, project="ai-sdlc-lab/demo-app", issue_id=9, target="WI-0001")
    assert ev.policy_decision == "blocked"
    assert "expired" in (ev.reason or "").lower()


def test_n06_duplicate_grant_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_control.approval.service import grant_approval

    calls = {"n": 0}

    def _append(*a, **k):
        calls["n"] += 1
        return Path("/tmp/x"), False

    monkeypatch.setattr(
        "agent_control.approval.service.resolve_plan_for_target",
        lambda *a, **k: _plan(),
    )
    monkeypatch.setattr(
        "agent_control.approval.service.load_approval",
        lambda *a, **k: _approval(),
    )
    monkeypatch.setattr("agent_control.approval.service.append_approval_granted", _append)
    monkeypatch.setattr("agent_control.approval.service._is_expired", lambda a: False)
    appr, msg, created = grant_approval(
        tmp_path,
        project="ai-sdlc-lab/demo-app",
        issue_id=9,
        target="WI-0001",
        approver_login="owner",
        author_is_owner=True,
    )
    assert appr is not None
    assert "idempotent" in msg.lower()
    assert created is False


def test_n07_approver_revoked_before_publish(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hermetic N07: publish recheck denies when recorded approver loses repo write."""
    from agent_control.authorization import recheck_publish_authorization
    from agent_control.config import Settings

    settings = Settings(
        GITEA_BOT_TOKEN="tok",
        GITEA_APPROVER_LOGINS="temp-approver",
        GITEA_ACTING_IDENTITY="agent-bot",
    )
    calls: list[tuple[str, str]] = []

    def _perm(project: str, username: str, *, need: str = "read", settings=None) -> bool:
        calls.append((username, need))
        if username == "agent-bot":
            return True
        if username == "temp-approver" and need == "write":
            return False  # collaborator revoked
        return username == "invoker"

    monkeypatch.setattr("agent_control.authorization.check_user_repo_permission", _perm)

    denied = recheck_publish_authorization(
        project="ai-sdlc-lab/demo-app",
        invoker_login="invoker",
        approver_login="temp-approver",
        source_sha="abc123",
        approval_valid=True,
        run_id="run-n07",
        settings=settings,
    )
    assert denied.decision == "deny"
    assert denied.approver_check.allowed is False
    assert "approver" in (denied.approver_check.reason or "").lower()
    assert ("temp-approver", "write") in calls

    # Control: same principal still authoritative when write remains.
    def _perm_ok(project: str, username: str, *, need: str = "read", settings=None) -> bool:
        return True

    monkeypatch.setattr("agent_control.authorization.check_user_repo_permission", _perm_ok)
    allowed = recheck_publish_authorization(
        project="ai-sdlc-lab/demo-app",
        invoker_login="invoker",
        approver_login="temp-approver",
        source_sha="abc123",
        approval_valid=True,
        run_id="run-n07b",
        settings=settings,
    )
    assert allowed.decision == "allow"
    assert allowed.approver_check.allowed is True


def test_n08_policy_pin_unavailable_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "agent_control.approval.service.resolve_plan_for_target",
        lambda *a, **k: _plan(),
    )
    monkeypatch.setattr(
        "agent_control.approval.service.load_approval",
        lambda *a, **k: _approval(policy_source_sha="c" * 40),
    )

    def _boom(*a, **k):
        raise RuntimeError("gitea down")

    monkeypatch.setattr("agent_control.project_registry.resolve_policy_source_pin", _boom)
    ev = evaluate_fix_request(tmp_path, project="ai-sdlc-lab/demo-app", issue_id=9, target="WI-0001")
    assert ev.policy_decision == "blocked"
    assert "fail closed" in (ev.reason or "").lower() or "unavailable" in (ev.reason or "").lower()


def test_ambiguous_patch_reconcile_advances_when_body_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = AgentSession(
        session_id="sess-rec",
        project="ai-sdlc-lab/demo-app",
        repo="demo-app",
        subject_kind="issue",
        subject_number=3,
        command_kind="review",
        status=SessionStatus.RUNNING,
        run_ids=["run-rec"],
        correlation_id="c",
        input_state_sha="a",
        head_sha="b",
        risk_level="risk1",
        invoked_by="alice",
        created_at="2026-07-21T00:00:00+00:00",
        updated_at="2026-07-21T00:00:00+00:00",
        session_comment_id=42,
        last_rendered_event_sequence=1,
        last_rendered_status="queued",
    )
    persist_session_with_run_index(tmp_path, session)

    monkeypatch.setenv("AGENT_STATE_ROOT", str(tmp_path))
    monkeypatch.setenv("GITEA_BOT_TOKEN", "tok")

    def _patch_timeout(*a, **k):
        raise GiteaHttpError(0, "timeout", retryable=True, ambiguous=True)

    monkeypatch.setattr(
        "agent_control.observe.comment_projection.patch_issue_comment",
        _patch_timeout,
    )
    monkeypatch.setattr(
        "agent_control.observe.comment_projection._reconcile_patch_applied",
        lambda *a, **k: True,
    )
    from agent_control.config import Settings

    settings = Settings(AGENT_STATE_ROOT=str(tmp_path), GITEA_BOT_TOKEN="tok")
    updated = project_session_comment(
        tmp_path,
        session,
        run_id="run-rec",
        command="review",
        display_status="running",
        event_sequence=2,
        settings=settings,
    )
    assert updated.last_rendered_event_sequence == 2
    assert updated.last_rendered_status == "running"


def test_reconcile_helper_compares_body(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Client:
        def get_issue_comment(self, owner, repo, comment_id):
            return {"body": "hello"}

    monkeypatch.setattr(
        "agent_control.gitea_client.GiteaClient",
        lambda settings=None: _Client(),
    )
    from agent_control.config import Settings

    settings = Settings(GITEA_BOT_TOKEN="tok")
    assert _reconcile_patch_applied("o/r", 1, "hello", settings=settings) is True
    assert _reconcile_patch_applied("o/r", 1, "other", settings=settings) is False


def test_dur_01_legacy_events_without_sequence_still_load(tmp_path: Path) -> None:
    """Legacy pre-sequence events remain readable after upgrade."""
    project = "ai-sdlc-lab/demo-app"
    owner, repo = project.split("/")
    day = tmp_path / "projects" / owner / repo / "events" / "2026" / "07" / "20"
    day.mkdir(parents=True)
    legacy = {
        "schema": "agent.event.v1",
        "event_id": "legacy1",
        "type": "agent.control_decision",
        "project": project,
        "payload": {"run_id": "run-leg", "kind": "other"},
        "recorded_at": "2026-07-20T00:00:00+00:00",
    }
    import json

    (day / "legacy1.json").write_text(json.dumps(legacy), encoding="utf-8")
    append_event(
        tmp_path,
        AgentEvent(
            event_id="new1",
            type="agent.control_decision",
            project=project,
            payload={"run_id": "run-leg", "kind": "other"},
        ),
    )
    loaded = load_project_events(tmp_path, project)
    ids = [e["event_id"] for e in loaded]
    assert "legacy1" in ids and "new1" in ids
    # Sequenced events come before unsequenced (sort_seq 10**12 for missing).
    assert ids.index("new1") < ids.index("legacy1")


def test_dur_02_migration_rerun_idempotent(tmp_path: Path) -> None:
    project = "ai-sdlc-lab/demo-app"
    e = AgentEvent(
        event_id="same",
        type="agent.control_decision",
        project=project,
        payload={"run_id": "r"},
    )
    p1, c1 = append_event(tmp_path, e)
    p2, c2 = append_event(tmp_path, e)
    assert c1 is True and c2 is False
    assert p1 == p2


def test_dur_03_restart_between_append_and_projection(tmp_path: Path) -> None:
    project = "ai-sdlc-lab/demo-app"
    append_event(
        tmp_path,
        AgentEvent(
            event_id="e1",
            type="agent.control_decision",
            project=project,
            payload={"run_id": "run-d3", "kind": "other"},
        ),
    )
    doc_a = build_observation_projection(tmp_path, project=project, run_id="run-d3")
    # "Restart": new process rebuilds from disk
    doc_b = build_observation_projection(tmp_path, project=project, run_id="run-d3")
    assert doc_a.events == doc_b.events


def test_dur_05_duplicate_budget_idempotency(tmp_path: Path) -> None:
    project = "ai-sdlc-lab/demo-app"
    limits = ModelAttemptBudget(max_total_completion_attempts=5, max_infrastructure_attempts=5)
    save_durable_budget(
        tmp_path, project=project, budget_key="run-d5", tracker=AttemptBudgetTracker(limits=limits)
    )
    ok1, t1 = reserve_attempt(
        tmp_path, project=project, budget_key="run-d5", kind="infrastructure", idempotency_key="k1"
    )
    ok2, t2 = reserve_attempt(
        tmp_path, project=project, budget_key="run-d5", kind="infrastructure", idempotency_key="k1"
    )
    assert ok1 and ok2
    assert t1.total_completion_attempts == t2.total_completion_attempts == 1


def test_dur_08_abandoned_invocation_listable(tmp_path: Path) -> None:
    from agent_control.invocation import begin_invocation, list_invocations
    from agent_shared.models.invocation import AgentIntent

    begin_invocation(
        tmp_path,
        project="ai-sdlc-lab/demo-app",
        raw_text="@agent maybe later",
        intent=AgentIntent(kind=None, confidence=0.2, natural_language_task="maybe later"),
    )
    rows = list_invocations(tmp_path, "ai-sdlc-lab/demo-app")
    assert len(rows) == 1
    assert rows[0].status == "intent_ambiguous"


def test_observe_invalid_shared_token_403(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Invalid bearer token, Gitea reachable and denying -> 403.

    Per V9 T05 response matrix, a 403 must only be returned when Gitea was
    actually reachable and *checked* the permission (and denied it) -- a
    permission check that could not be performed (Gitea unreachable/DNS
    down) must map to 503 instead (see
    ``test_v9_t05_oauth_shell.py`` and ``agent_control.observe.auth``
    module docstring). Mock Gitea as reachable-but-denying here so this
    test exercises the 403 branch deterministically, independent of
    whether the sandbox running CI has DNS access to the real Gitea host.
    """
    monkeypatch.setenv("AGENT_STATE_ROOT", str(tmp_path))
    monkeypatch.setenv("OBSERVE_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OBSERVE_SHARED_TOKEN", "good-token")
    from unittest.mock import patch as mock_patch

    from agent_control.config import Settings
    from fastapi import HTTPException

    settings = Settings(
        AGENT_STATE_ROOT=str(tmp_path),
        OBSERVE_REQUIRE_AUTH=True,
        OBSERVE_SHARED_TOKEN="good-token",
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"permissions": {"pull": False, "push": False, "admin": False}}
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.get.return_value = mock_resp

    with mock_patch("httpx.Client", return_value=mock_client):
        with pytest.raises(HTTPException) as ei:
            require_observe_repo_read(
                "ai-sdlc-lab/demo-app",
                authorization="Bearer bad-token",
                settings=settings,
            )
    assert ei.value.status_code == 403


def test_observe_missing_auth_401(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_control.config import Settings
    from fastapi import HTTPException

    settings = Settings(AGENT_STATE_ROOT=str(tmp_path), OBSERVE_REQUIRE_AUTH=True)
    with pytest.raises(HTTPException) as ei:
        require_observe_repo_read("ai-sdlc-lab/demo-app", settings=settings)
    assert ei.value.status_code == 401
