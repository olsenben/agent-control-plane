"""Tests for dispatch payload building."""

from unittest.mock import patch

from agent_control.project_registry import PolicySourcePin
from agent_control.workflows.dispatch import build_rlm_job
from agent_shared.models.intent import CommandIntent
from agent_shared.models.state import VerificationState

_FAKE_PIN = PolicySourcePin(
    policy_source_repo="ai-sdlc-lab/demo-app",
    policy_source_remote="http://192.168.4.60:3000/ai-sdlc-lab/demo-app",
    policy_source_ref="main",
    policy_source_sha="0123456789abcdef0123456789abcdef01234567",
)


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
    with patch(
        "agent_control.workflows.dispatch.resolve_policy_source_pin",
        return_value=_FAKE_PIN,
    ):
        job = build_rlm_job(state, trigger)
    assert job is not None
    assert job.schema_version == "rlm_job.v1"
    assert job.run_id == "run-evt123"
    assert job.job_id == "rlm-root-evt123"
    assert job.risk_class == "read_only"
    assert job.model_policy == "fake"
    assert job.trigger_context.issue_number == 12
    assert job.policy_source_sha == _FAKE_PIN.policy_source_sha
    assert job.policy_source_ref == "main"
    assert job.policy_ref == "main"
    assert job.policy_schema_version == "policy_source.v1"


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
    trigger = {
        "event_id": "x",
        "type": "gitea.issue_comment",
        "project": "ai-sdlc-lab/demo-app",
        "payload": {},
    }
    assert build_rlm_job(state, trigger) is None
