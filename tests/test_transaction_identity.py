"""Identity principals and TB1 worker credential helper."""

from __future__ import annotations

from agent_control.transaction.identity import (
    attribution,
    control_plane,
    fixture_actor_identity,
    human_initiator,
    verifier,
    worker_credential_assertion,
)
from agent_shared.models.transaction.task import PolicyContext, RequestedChange, TaskEnvelope


def test_principals_recorded_on_task_envelope() -> None:
    human = human_initiator("alice")
    actor = fixture_actor_identity(run_id="r1")
    plane = control_plane()
    identity = attribution(on_behalf_of=human, executed_by=actor, authorized_by=plane)
    envelope = TaskEnvelope(
        task_id="t1",
        tenant_id="tenant",
        org_id="org",
        repository="org/repo",
        source_sha="abc1234",
        task_provider="GITEA_ISSUE",
        provider_task_id="12",
        human_initiator=human,
        initiator_identity="alice",
        identity=identity,
        task_type="FUNCTIONAL_MAINTENANCE",
        requested_change=RequestedChange(summary="fix foo"),
        policy_context=PolicyContext(
            policy_id="w5_evidence_policy.v1",
            policy_version="v1",
            policy_digest="a" * 64,
            admission_implementation_digest="b" * 64,
        ),
        created_at="2026-08-24T00:00:00+00:00",
        task_digest="c" * 64,
    )
    assert envelope.identity is not None
    assert envelope.identity.ON_BEHALF_OF.principal_kind == "HUMAN_INITIATOR"
    assert envelope.identity.EXECUTED_BY.principal_kind == "AGENT_WORKER"
    assert envelope.identity.AUTHORIZED_BY is not None
    assert envelope.identity.AUTHORIZED_BY.principal_kind == "CONTROL_PLANE"
    assert envelope.tenant_id == "tenant"
    assert envelope.repository == "org/repo"


def test_tb1_worker_has_no_durable_token() -> None:
    result = worker_credential_assertion(env={})
    assert result["WORKER_DURABLE_CREDENTIALS_PRESENT"] == "NO"
    assert result["ok"] is True


def test_tb1_forbidden_env_fail_closed() -> None:
    result = worker_credential_assertion(env={"GITEA_BOT_TOKEN": "x"})
    assert result["ok"] is False
    assert result["WORKER_DURABLE_CREDENTIALS_PRESENT"] == "YES"


def test_verified_by_and_published_by_optional() -> None:
    human = human_initiator("alice")
    actor = fixture_actor_identity(run_id="r1")
    plane = control_plane()
    identity = attribution(on_behalf_of=human, executed_by=actor, authorized_by=plane)
    assert identity.verified_by is None
    assert identity.published_by is None
    assert identity.initiated_by is identity.ON_BEHALF_OF
    assert identity.executed_by is identity.EXECUTED_BY
    assert identity.authorized_by is identity.AUTHORIZED_BY
    verifier_p = verifier("ct102-actions")
    publisher = control_plane()
    full = attribution(
        on_behalf_of=human,
        executed_by=actor,
        authorized_by=plane,
        verified_by=verifier_p,
        published_by=publisher,
    )
    assert full.verified_by is not None
    assert full.verified_by.principal_kind == "VERIFIER"
    assert full.published_by is not None
    assert full.published_by.principal_kind == "CONTROL_PLANE"
    assert full.initiated_by.identity_id == "alice"
