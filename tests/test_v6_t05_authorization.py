"""V6 T05 authorization_decision.v1 + commit trailers."""

from __future__ import annotations

from agent_shared.models.approval import FixAuthorizationBinding
from agent_shared.models.authorization_decision import evaluate_authorization
from agent_workers.publish.formatters import build_commit_message


def test_authorization_plan_allows_read_only_invoker() -> None:
    decision = evaluate_authorization(
        command_kind="plan",
        project="demo/demo-app",
        invoker_login="reader",
        invoker_can_read=True,
        invoker_is_approver=False,
        approver_login=None,
        acting_identity="agent-bot",
        bot_can_write=False,
        policy_permits=True,
        require_approver=False,
        require_bot_write=False,
    )
    assert decision.decision == "allow"
    assert decision.invoker_check.allowed is True
    assert decision.acting_identity_check.reason == "mutation not required"


def test_authorization_approve_requires_approver_authority() -> None:
    denied = evaluate_authorization(
        command_kind="approve",
        project="demo/demo-app",
        invoker_login="reader",
        invoker_can_read=True,
        invoker_is_approver=False,
        approver_login="reader",
        acting_identity="agent-bot",
        bot_can_write=True,
        policy_permits=True,
        require_approver=True,
        require_bot_write=False,
    )
    assert denied.decision == "deny"
    assert denied.invoker_check.allowed is False

    allowed = evaluate_authorization(
        command_kind="approve",
        project="demo/demo-app",
        invoker_login="owner",
        invoker_can_read=True,
        invoker_is_approver=True,
        approver_login="owner",
        acting_identity="agent-bot",
        bot_can_write=True,
        policy_permits=True,
        require_approver=True,
        require_bot_write=False,
    )
    assert allowed.decision == "allow"


def test_authorization_publish_separate_predicates_and_sha_drift() -> None:
    ok = evaluate_authorization(
        command_kind="publish",
        project="demo/demo-app",
        invoker_login="reader",
        invoker_can_read=True,
        invoker_is_approver=False,
        approver_login="owner",
        acting_identity="agent-bot",
        bot_can_write=True,
        policy_permits=True,
        approval_valid=True,
        require_approver=True,
        require_bot_write=True,
        approver_is_authority=True,
        source_sha="abc",
    )
    assert ok.decision == "allow"
    assert ok.invoker_check.allowed is True
    assert ok.approver_check.allowed is True
    assert ok.acting_identity_check.allowed is True

    drift = evaluate_authorization(
        command_kind="publish",
        project="demo/demo-app",
        invoker_login="reader",
        invoker_can_read=True,
        invoker_is_approver=False,
        approver_login="owner",
        acting_identity="agent-bot",
        bot_can_write=True,
        policy_permits=True,
        approval_valid=False,
        approval_reason="source_sha_drift",
        require_approver=True,
        require_bot_write=True,
        approver_is_authority=True,
        source_sha="abc",
    )
    assert drift.decision == "deny"
    assert drift.approval_scope.allowed is False


def test_commit_trailers_include_identity() -> None:
    binding = FixAuthorizationBinding(
        approval_id="appr-1",
        approval_target_id="tgt-1",
        plan_run_id="run-plan-1",
        plan_hash="ph",
        blast_radius_hash="br",
        allowed_files=["a.py"],
        approved_base_sha="abc123",
        approved_base_ref="main",
    )
    msg = build_commit_message(
        run_id="run-fix-1",
        binding=binding,
        approved_base_sha="abc123",
        invoked_by="alice",
        session_id="sess-xyz",
        approved_by="owner",
    )
    assert "Agent-Run: run-fix-1" in msg
    assert "Agent-Session: sess-xyz" in msg
    assert "Invoked-By: alice" in msg
    assert "Approved-By: owner" in msg
    assert "Agent-Run-ID: run-fix-1" in msg
