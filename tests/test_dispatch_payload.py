"""Tests for dispatch payload building."""

from agent_control.workflows.dispatch import build_rlm_job
from agent_shared.models.intent import CommandIntent
from agent_shared.models.state import VerificationState


def test_build_rlm_job_inspect() -> None:
    state = VerificationState(
        project="ai-sdlc-lab/demo-app",
        command_intent=CommandIntent(
            activated=True,
            activation="/agent",
            kind="inspect",
            natural_language_task="why idle",
            confidence=1.0,
        ),
        dispatch_recommended=True,
        dispatch_kind="inspect",
    )
    trigger = {
        "event_id": "evt123",
        "delivery_id": "del123",
        "type": "gitea.issue_comment",
        "project": "ai-sdlc-lab/demo-app",
        "payload": {
            "comment": {"body": "/agent inspect why idle", "id": 99},
            "issue": {"number": 12},
            "repository": {"full_name": "ai-sdlc-lab/demo-app"},
        },
    }
    job = build_rlm_job(state, trigger)
    assert job is not None
    assert job.schema_version == "rlm_job.v1"
    assert job.run_id == "run-evt123"
    assert job.job_id == "rlm-root-evt123"
    assert job.risk_class == "read_only"
    assert job.model_policy == "fake"
    assert job.trigger_context.issue_number == 12


def test_build_rlm_job_blocks_fix() -> None:
    state = VerificationState(
        project="ai-sdlc-lab/demo-app",
        command_intent=CommandIntent(
            activated=True,
            activation="/agent",
            kind="fix",
            natural_language_task="WI-0004-dc0b71eb",
            approval_target="WI-0004-dc0b71eb",
            confidence=1.0,
        ),
        dispatch_recommended=True,
    )
    trigger = {"event_id": "x", "type": "gitea.issue_comment", "project": "ai-sdlc-lab/demo-app", "payload": {}}
    assert build_rlm_job(state, trigger) is None
