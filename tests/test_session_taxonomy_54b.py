"""Slice 5.4b session terminal taxonomy tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_control.approval.handlers import handle_approval_commands
from agent_control.events import load_project_events
from agent_control.publish.broker import broker_publish_fix
from agent_control.session import (
    SessionTerminalError,
    SessionTerminalReason,
    begin_typed_session,
    classify_broker_reject,
    finalize_session_blocked,
    handle_publish_session_terminal,
    load_session,
    normalize_terminal,
)
from agent_control.session.reasons import ALLOWED_REASONS_BY_STATUS, classify_unsuccessful_terminal
from agent_shared.bundles import write_ready_bundle
from agent_shared.models.agent_session import SessionStatus
from agent_shared.models.intent import CommandIntent
from conftest import seed_plan_completed
from support.policy_pin import install_fake_policy_pin


def test_allowed_reason_status_matrix() -> None:
    assert SessionTerminalReason.INGEST_COMPLETED in ALLOWED_REASONS_BY_STATUS["finished"]
    assert SessionTerminalReason.CI_VERIFIED in ALLOWED_REASONS_BY_STATUS["finished"]
    assert SessionTerminalReason.VERIFICATION_FAILED in ALLOWED_REASONS_BY_STATUS["failed"]
    assert SessionTerminalReason.VERIFICATION_MISSING in ALLOWED_REASONS_BY_STATUS["blocked"]
    assert SessionTerminalReason.WORKER_FAILED in ALLOWED_REASONS_BY_STATUS["failed"]
    assert SessionTerminalReason.POLICY_DENIED in ALLOWED_REASONS_BY_STATUS["blocked"]
    assert SessionTerminalReason.PUBLISH_SUCCEEDED not in ALLOWED_REASONS_BY_STATUS["finished"]


def test_invalid_status_reason_combo_rejected() -> None:
    with pytest.raises(SessionTerminalError):
        normalize_terminal("finished", SessionTerminalReason.WORKER_FAILED)


def test_unknown_domain_reason_maps_to_canonical_fallback() -> None:
    status, reason = classify_unsuccessful_terminal(
        domain_reasons=["brand_new_upstream_code"],
        policy_decision=None,
    )
    assert status == "failed"
    assert reason == SessionTerminalReason.SESSION_FAILED


def test_finalize_session_blocked_emits_ledger(tmp_path: Path) -> None:
    from agent_control.session import begin_typed_session
    from agent_shared.models.jobs import TriggerContext

    state = tmp_path / "agent-state"
    state.mkdir()
    tc = TriggerContext(
        event_type="gitea.issue_comment",
        issue_number=2,
        author="alice",
        raw_body="/agent fix",
        normalized_body="/agent fix",
    )
    session = begin_typed_session(
        state,
        project="ai-sdlc-lab/demo-app",
        command_kind="fix",
        run_id="run-block1",
        head_sha="abc",
        trigger_context=tc,
    )
    finalize_session_blocked(
        state,
        session,
        run_id="run-block1",
        reason_code=SessionTerminalReason.HUMAN_APPROVAL_REQUIRED,
        reason="no approval",
    )
    loaded = load_session(state, "ai-sdlc-lab/demo-app", session.session_id)
    assert loaded is not None
    assert loaded.status == SessionStatus.BLOCKED
    events = load_project_events(state, "ai-sdlc-lab/demo-app")
    assert sum(1 for e in events if e["type"] == "agent.session_blocked") == 1


def test_fix_blocked_without_approval_creates_session_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fake_policy_pin(monkeypatch)
    target = seed_plan_completed(tmp_path)
    trigger = {
        "event_id": "fix-no-appr",
        "payload": {
            "comment": {"body": f"/agent fix {target}", "id": 501},
            "issue": {"number": 4},
        },
    }
    intent = CommandIntent(
        activated=True,
        activation="/agent",
        kind="fix",
        approval_target=target,
        natural_language_task=target,
        confidence=1.0,
    )
    result = handle_approval_commands(
        tmp_path,
        "ai-sdlc-lab/agent-control-plane",
        trigger,
        intent,
    )
    assert result["terminal_reason_code"] == "human_approval_required"
    session = load_session(tmp_path, "ai-sdlc-lab/agent-control-plane", result["session_id"])
    assert session is not None
    assert session.status == SessionStatus.BLOCKED
    events = load_project_events(tmp_path, "ai-sdlc-lab/agent-control-plane")
    assert sum(1 for e in events if e["type"] == "agent.session_blocked") == 1


def test_replayed_blocked_fix_command_does_not_duplicate_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fake_policy_pin(monkeypatch)
    target = seed_plan_completed(tmp_path)
    trigger = {
        "event_id": "fix-replay",
        "payload": {
            "comment": {"body": f"/agent fix {target}", "id": 777},
            "issue": {"number": 4},
        },
    }
    intent = CommandIntent(
        activated=True,
        activation="/agent",
        kind="fix",
        approval_target=target,
        natural_language_task=target,
        confidence=1.0,
    )
    r1 = handle_approval_commands(tmp_path, "ai-sdlc-lab/agent-control-plane", trigger, intent)
    r2 = handle_approval_commands(tmp_path, "ai-sdlc-lab/agent-control-plane", trigger, intent)
    assert r1["session_id"] == r2["session_id"]
    events = load_project_events(tmp_path, "ai-sdlc-lab/agent-control-plane")
    assert sum(1 for e in events if e["type"] == "agent.session_blocked") == 1


def test_stale_base_reject_maps_publish_failed_not_blocked() -> None:
    terminal, reason = classify_broker_reject(broker_reason="stale_base")
    assert terminal == "failed"
    assert reason == SessionTerminalReason.PUBLISH_FAILED


def test_publish_attestation_deny_fix_session_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_policy_pin(monkeypatch)
    state = tmp_path / "agent-state"
    state.mkdir()
    from agent_shared.models.jobs import TriggerContext

    session = begin_typed_session(
        state,
        project="ai-sdlc-lab/demo-app",
        command_kind="fix",
        run_id="run-pub-deny",
        head_sha="abc",
        trigger_context=TriggerContext(
            event_type="gitea.issue_comment",
            issue_number=2,
            author="alice",
            raw_body="/agent fix",
            normalized_body="/agent fix",
        ),
    )
    write_ready_bundle(
        state,
        run_id="run-pub-deny",
        kind="fix",
        attempt_id="1",
        producer_base_sha="abc",
        patch_bytes=b"diff --git a/a b/a\n--- a/a\n+++ b/a\n@@ -0,0 +1 @@\n+a\n",
    )
    from agent_control.publish.state import try_enqueue_cas

    try_enqueue_cas(
        state,
        run_id="run-pub-deny",
        kind="fix",
        attempt_id="1",
        bundle_id="ignored",
        project="ai-sdlc-lab/demo-app",
    )
    manifest = write_ready_bundle(
        state,
        run_id="run-pub-deny",
        kind="fix",
        attempt_id="1",
        producer_base_sha="abc",
        patch_bytes=b"diff --git a/a b/a\n--- a/a\n+++ b/a\n@@ -0,0 +1 @@\n+a\n",
    )
    from agent_control.publish.state import save_publish_record
    from agent_shared.models.publish import PublishRecord

    save_publish_record(
        state,
        PublishRecord(
            run_id="run-pub-deny",
            bundle_id=manifest.bundle_id,
            kind="fix",
            attempt_id="1",
            publish_state="queued",
            project="ai-sdlc-lab/demo-app",
            approval_target_id="target-1",
        ),
    )
    out = broker_publish_fix(
        state_root=state,
        run_id="run-pub-deny",
        attempt_id="1",
        bundle_id=manifest.bundle_id,
    )
    assert out["ok"] is False
    loaded = load_session(state, "ai-sdlc-lab/demo-app", session.session_id)
    assert loaded is not None
    assert loaded.status == SessionStatus.BLOCKED
    assert loaded.terminal_reason_code == "sandbox_unavailable"


def test_broker_retry_after_blocked_terminal_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_policy_pin(monkeypatch)
    state = tmp_path / "agent-state"
    state.mkdir()
    from agent_shared.models.jobs import TriggerContext

    session = begin_typed_session(
        state,
        project="ai-sdlc-lab/demo-app",
        command_kind="fix",
        run_id="run-retry",
        head_sha="abc",
        trigger_context=TriggerContext(
            event_type="gitea.issue_comment",
            issue_number=2,
            author="alice",
            raw_body="/agent fix",
            normalized_body="/agent fix",
        ),
    )
    handle_publish_session_terminal(
        state,
        project="ai-sdlc-lab/demo-app",
        run_id="run-retry",
        terminal="blocked",
        reason_code=SessionTerminalReason.SANDBOX_UNAVAILABLE,
        domain_reasons=["sandbox_attestation_missing"],
    )
    handle_publish_session_terminal(
        state,
        project="ai-sdlc-lab/demo-app",
        run_id="run-retry",
        terminal="blocked",
        reason_code=SessionTerminalReason.SANDBOX_UNAVAILABLE,
        domain_reasons=["sandbox_attestation_missing"],
    )
    events = load_project_events(state, "ai-sdlc-lab/demo-app")
    assert sum(1 for e in events if e["type"] == "agent.session_blocked") == 1
    loaded = load_session(state, "ai-sdlc-lab/demo-app", session.session_id)
    assert loaded is not None
    assert loaded.status == SessionStatus.BLOCKED
