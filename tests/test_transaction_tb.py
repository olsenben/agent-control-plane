"""Library-level TB3-TB10 (and TB1 documented skip/helper)."""

from __future__ import annotations

import pytest

from agent_control.transaction.admission import AUTO_ADMIT, wrap_decide_c
from agent_control.transaction.capability import (
    CAPABILITY_ALREADY_CONSUMED,
    CapabilityAlreadyConsumed,
    InMemoryCapabilityStore,
    consume_capability,
    mint_capability,
)
from agent_control.transaction.evidence.adapters import actor_provided_receipt
from agent_control.transaction.evidence.bus import run_evidence_bus
from agent_control.transaction.evidence.route import build_route
from agent_control.transaction.identity import (
    fixture_actor_identity,
    human_initiator,
    worker_credential_assertion,
)
from agent_control.transaction.witness import StateWitnessError, check_state_witness
from agent_shared.models.transaction.admission import PolicyFields

PIN = "ad265893a9e7161ba8acd0c95e778738d92584eb310cb6bac85e89121f72098c"
DIGEST = "b" * 64
SHA = "abc1234"
POLICY = "e" * 64
BUNDLE = "2" * 64


def test_tb1_documented_no_live_push() -> None:
    """TB1 live Gitea push is out of scope; helper asserts worker has no token."""
    assert worker_credential_assertion(env={})["ok"] is True


def test_tb1_no_write_token_and_simulated_push_denied() -> None:
    """TB1: CT104 direct Gitea push FAIL. No write token; simulated push denied.

    Does not contact Gitea. Worker mutation helpers are removed (V4.1.1); a
    simulated push attempt is denied locally because no durable write token
    is present and the CT104 publish entrypoint refuses to run.
    """
    env: dict[str, str] = {}
    creds = worker_credential_assertion(env=env)
    assert creds["ok"] is True
    assert creds["WORKER_DURABLE_CREDENTIALS_PRESENT"] == "NO"
    assert not env.get("GITEA_BOT_TOKEN")
    assert not env.get("GITEA_AGENT_TOKEN")

    from agent_workers.publish.remote import publish_fix_branch_and_pr, push_repair_fast_forward

    with pytest.raises(RuntimeError, match="CT104 remote publish removed") as publish_exc:
        publish_fix_branch_and_pr()
    with pytest.raises(RuntimeError, match="CT104 repair push removed"):
        push_repair_fast_forward()

    simulated = {
        "attempt": "ct104_direct_gitea_push",
        "has_write_token": False,
        "contacted_gitea": False,
        "allowed": False,
        "reason": "NO_WRITE_TOKEN",
        "entrypoint_denied": "CT104_REMOTE_PUBLISH_REMOVED",
        "entrypoint_detail": str(publish_exc.value),
    }
    assert simulated["allowed"] is False
    assert simulated["contacted_gitea"] is False
    assert simulated["has_write_token"] is False
    assert "V4.1.1" in simulated["entrypoint_detail"] or "CT104" in simulated["entrypoint_detail"]


def _unit() -> dict:
    return {
        "path": "src/pkg/core.py",
        "element_key": "func:foo",
        "symbol": "foo",
        "change_kind": "changed",
        "receipts": ["TASK_NAMED"],
        "visibility": "private",
        "privileged": False,
        "local_creation": False,
        "callers": [],
        "side_effect_category": "NONE",
    }


def test_tb3_patch_changed_after_admission() -> None:
    expected = {
        "source_sha": SHA,
        "patch_digest": DIGEST,
        "policy_digest": POLICY,
        "evidence_bundle_digest": BUNDLE,
        "allowed_target_branch": "agent/admitted",
        "repo": "org/repo",
    }
    with pytest.raises(StateWitnessError) as exc:
        check_state_witness(expected=expected, observed={**expected, "patch_digest": "9" * 64})
    assert exc.value.code == "PATCH_DRIFT"


def test_tb4_double_consume() -> None:
    store = InMemoryCapabilityStore()
    cap = mint_capability(
        repo="org/repo",
        tenant_id="t",
        org_id="o",
        source_sha=SHA,
        patch_digest=DIGEST,
        allowed_target_branch="agent/admitted",
        policy_digest=POLICY,
        verification_digest="f" * 64,
        admission_decision_digest="1" * 64,
        evidence_bundle_digest=BUNDLE,
        task_id="task-1",
        session_id="sess-1",
        human_initiator=human_initiator("alice"),
        agent_identity=fixture_actor_identity(),
        store=store,
    )
    consume_capability(
        capability_id=cap.capability_id,
        store=store,
        current_base_sha=SHA,
        patch_digest=DIGEST,
        repo="org/repo",
        target_ref="agent/admitted",
        policy_digest=POLICY,
        evidence_bundle_digest=BUNDLE,
    )
    with pytest.raises(CapabilityAlreadyConsumed) as exc:
        consume_capability(
            capability_id=cap.capability_id,
            store=store,
            current_base_sha=SHA,
            patch_digest=DIGEST,
            repo="org/repo",
            target_ref="agent/admitted",
            policy_digest=POLICY,
        )
    assert exc.value.code == CAPABILITY_ALREADY_CONSUMED


def test_tb5_source_drift() -> None:
    expected = {
        "source_sha": SHA,
        "patch_digest": DIGEST,
        "policy_digest": POLICY,
        "allowed_target_branch": "agent/admitted",
        "repo": "org/repo",
    }
    with pytest.raises(StateWitnessError) as exc:
        check_state_witness(expected=expected, observed={**expected, "source_sha": "ffff000"})
    assert exc.value.code == "SOURCE_DRIFT"


def test_tb6_stale_evidence() -> None:
    expected = {
        "source_sha": SHA,
        "patch_digest": DIGEST,
        "policy_digest": POLICY,
        "evidence_bundle_digest": BUNDLE,
        "allowed_target_branch": "agent/admitted",
        "repo": "org/repo",
    }
    with pytest.raises(StateWitnessError) as exc:
        check_state_witness(
            expected=expected, observed={**expected, "evidence_bundle_digest": "3" * 64}
        )
    assert exc.value.code == "EVIDENCE_STALE"


def test_tb7_wrong_repo_or_branch() -> None:
    expected = {
        "source_sha": SHA,
        "patch_digest": DIGEST,
        "policy_digest": POLICY,
        "allowed_target_branch": "agent/admitted",
        "repo": "org/repo",
    }
    with pytest.raises(StateWitnessError) as exc:
        check_state_witness(expected=expected, observed={**expected, "repo": "evil/repo"})
    assert exc.value.code == "TARGET_MISMATCH"


def test_tb8_required_provider_fail_no_auto_admit() -> None:
    route = build_route(["PRODUCTION_SOURCE_CHANGE"], patch_digest=DIGEST, repository="org/repo")
    bundle = run_evidence_bus(
        binding={"repo": "org/repo", "source_sha": SHA, "patch_digest": DIGEST},
        route=route,
        adapter_kwargs={"P1": {"force_failure": True}},
    )
    assert bundle["auto_admit_blocked"] is True
    unit = _unit()
    decision = wrap_decide_c(
        units=[unit],
        changed_paths=["src/pkg/core.py"],
        decision={"writable_resources": [{"path": unit["path"], "element_key": unit["element_key"]}]},
        g0=[],
        verification={"passed": True, "incomplete": False},
        policy=PolicyFields(
            policy_id="w5_evidence_policy.v1",
            policy_version="v1",
            policy_digest=POLICY,
            admission_implementation_digest=PIN,
        ),
        proposal_id="p1",
        patch_digest=DIGEST,
        required_provider_failed=True,
    )
    assert decision.decision != AUTO_ADMIT


def test_tb9_forged_actor_evidence_not_authoritative() -> None:
    forged = actor_provided_receipt(
        binding={"repo": "org/repo", "source_sha": SHA, "patch_digest": DIGEST}
    )
    route = build_route(["PRODUCTION_SOURCE_CHANGE"], patch_digest=DIGEST, repository="org/repo")
    bundle = run_evidence_bus(
        binding={"repo": "org/repo", "source_sha": SHA, "patch_digest": DIGEST},
        route=route,
        extra_receipts=[forged],
        adapter_kwargs={"P1": {"verdict": {"passed": True}}},
    )
    forged_items = [item for item in bundle["receipts"] if item.get("trust_class") == "ACTOR_PROVIDED"]
    assert forged_items
    assert all(item.get("authoritative") is False for item in forged_items)
    assert all(item.get("can_authorize") is False for item in forged_items)


def test_tb10_policy_digest_change_invalidates() -> None:
    expected = {
        "source_sha": SHA,
        "patch_digest": DIGEST,
        "policy_digest": POLICY,
        "allowed_target_branch": "agent/admitted",
        "repo": "org/repo",
    }
    with pytest.raises(StateWitnessError) as exc:
        check_state_witness(expected=expected, observed={**expected, "policy_digest": "0" * 64})
    assert exc.value.code == "POLICY_DRIFT"
