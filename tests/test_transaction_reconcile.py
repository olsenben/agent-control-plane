"""Deterministic Gitea reconcile and PUBLISH_REQUESTED intent."""

from __future__ import annotations

from pathlib import Path

from agent_control.transaction.ledger import (
    EVENT_PUBLISH_REQUESTED,
    record_publish_requested,
    stable_publish_effect_id,
)
from agent_control.transaction.reconcile import (
    ExpectedPublishEffect,
    ObservedGitea,
    inspect_expected_effect,
    transaction_marker,
)
from agent_control.events import load_project_events
from agent_control.publish.state import load_publish_intent


PROJECT = "org/repo"


def test_already_applied_when_branch_sha_matches() -> None:
    expected = ExpectedPublishEffect(
        repo=PROJECT,
        branch="agent/admitted",
        commit_sha="abc1234",
        run_id="run-1",
        bundle_id="b1",
        marker=transaction_marker(run_id="run-1", bundle_id="b1"),
    )
    observed = ObservedGitea(
        branch_exists=True,
        branch_sha="abc1234",
        prs=(
            {
                "body": "<!-- agent-run-id:run-1 bundle-id:b1 -->",
                "head": {"ref": "agent/admitted", "sha": "abc1234"},
            },
        ),
    )
    decision = inspect_expected_effect(expected, observed)
    assert decision.status == "ALREADY_APPLIED"
    assert decision.already_applied is True
    assert decision.next_action == "NO_RETRY"


def test_not_applied_allows_retry_push() -> None:
    expected = ExpectedPublishEffect(
        repo=PROJECT,
        branch="agent/admitted",
        commit_sha="abc1234",
        run_id="run-1",
    )
    observed = ObservedGitea(branch_exists=False, branch_sha=None, prs=())
    decision = inspect_expected_effect(expected, observed)
    assert decision.status == "NOT_APPLIED"
    assert decision.next_action == "RETRY_PUSH"


def test_ambiguous_read_does_not_blindly_retry() -> None:
    expected = ExpectedPublishEffect(
        repo=PROJECT,
        branch="agent/admitted",
        commit_sha="abc1234",
        run_id="run-1",
    )
    observed = ObservedGitea(read_error="TimeoutException")
    decision = inspect_expected_effect(expected, observed)
    assert decision.status == "STILL_AMBIGUOUS"
    assert decision.next_action == "RECONCILE_BEFORE_RETRY"
    assert decision.retry_class == "RECONCILE_BEFORE_RETRY"


def test_branch_sha_mismatch_is_permanent_conflict() -> None:
    expected = ExpectedPublishEffect(
        repo=PROJECT,
        branch="agent/admitted",
        commit_sha="abc1234",
        run_id="run-1",
    )
    observed = ObservedGitea(branch_exists=True, branch_sha="ffff9999", prs=())
    decision = inspect_expected_effect(expected, observed)
    assert decision.status == "CONFLICT"
    assert decision.next_action == "OPERATOR_INTERVENTION"
    assert decision.retry_class == "PERMANENT"


def test_publish_requested_reuses_stable_effect_id(tmp_path: Path) -> None:
    state = tmp_path / "state"
    kwargs = {
        "state_root": state,
        "project": PROJECT,
        "transaction_id": "tx-1",
        "capability_id": "cap-1",
        "patch_digest": "a" * 64,
        "repo": PROJECT,
        "source_sha": "deadbee",
        "target_branch": "agent/admitted",
        "expected_commit_sha": "c" * 40,
        "run_id": "run-1",
        "bundle_id": "bundle-1",
        "kind": "fix",
    }
    first = record_publish_requested(**kwargs)
    second = record_publish_requested(**kwargs)
    assert first == second
    expected = stable_publish_effect_id(
        transaction_id="tx-1",
        capability_id="cap-1",
        patch_digest="a" * 64,
        repo=PROJECT,
        source_sha="deadbee",
        target_branch="agent/admitted",
    )
    assert first == expected
    intent = load_publish_intent(state, PROJECT, "c" * 40)
    assert intent is not None
    assert intent.publish_effect_id == first
    events = load_project_events(state, PROJECT)
    publish_events = [
        item
        for item in events
        if item.get("type") == "transaction_control_event.v1"
        or item.get("raw_event_type") == EVENT_PUBLISH_REQUESTED
    ]
    assert len(publish_events) == 1
    payload = publish_events[0]["payload"]
    assert payload["event_type"] == EVENT_PUBLISH_REQUESTED
    assert payload["payload"]["publish_effect_id"] == first
    assert payload["payload"]["transaction_id"] == "tx-1"
    assert payload["payload"]["capability_id"] == "cap-1"
    assert payload["payload"]["patch_digest"] == "a" * 64
    assert payload["payload"]["target_branch"] == "agent/admitted"
