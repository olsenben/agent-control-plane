"""Evidence bus fail-closed and ACTOR_PROVIDED non-authority."""

from __future__ import annotations

from agent_control.transaction.evidence.adapters import actor_provided_receipt
from agent_control.transaction.evidence.bus import run_evidence_bus
from agent_control.transaction.evidence.receipts import TRUST_ACTOR_PROVIDED
from agent_control.transaction.evidence.route import build_route, classify_change_classes

DIGEST = "c" * 64
SHA = "abc1234"


def _binding() -> dict:
    return {"repo": "org/repo", "source_sha": SHA, "patch_digest": DIGEST}


def test_required_provider_fail_blocks_auto_admit() -> None:
    route = build_route(["PRODUCTION_SOURCE_CHANGE"], patch_digest=DIGEST, repository="org/repo")
    bundle = run_evidence_bus(
        binding=_binding(),
        route=route,
        adapter_kwargs={"P1": {"force_failure": True}},
    )
    assert "P1" in bundle["required_provider_failures"]
    assert bundle["auto_admit_blocked"] is True
    assert "TOOL_FAILURE" in bundle["incomplete_reasons"]


def test_required_provider_timeout_fail_closed() -> None:
    route = build_route(
        ["SECURITY_FINDING_TASK"],
        patch_digest=DIGEST,
        repository="org/repo",
    )
    bundle = run_evidence_bus(
        binding=_binding(),
        route=route,
        adapter_kwargs={"P2": {"force_timeout": True}, "P3": {"force_failure": False}},
    )
    assert bundle["auto_admit_blocked"] is True
    assert "P2" in bundle["required_provider_failures"]


def test_required_provider_malformed_fail_closed() -> None:
    route = build_route(
        ["SECURITY_FINDING_TASK"],
        patch_digest=DIGEST,
        repository="org/repo",
    )
    bundle = run_evidence_bus(
        binding=_binding(),
        route=route,
        adapter_kwargs={"P2": {"malformed": True}},
    )
    assert bundle["auto_admit_blocked"] is True
    assert "P2" in bundle["required_provider_failures"]


def test_unbound_required_receipt_fail_closed() -> None:
    route = build_route(["PRODUCTION_SOURCE_CHANGE"], patch_digest=DIGEST, repository="org/repo")
    unbound = actor_provided_receipt(binding={"repo": "other/repo", "source_sha": SHA, "patch_digest": DIGEST})
    unbound["trust_class"] = "AUTHORITATIVE_CI"
    unbound["producer"] = {"name": "P1", "trust_class": "AUTHORITATIVE_CI"}
    unbound["schema"] = "verification_evidence.v1"
    bundle = run_evidence_bus(
        binding=_binding(),
        route=route,
        extra_receipts=[unbound],
        adapter_kwargs={"P1": {"force_failure": True}},
    )
    assert bundle["auto_admit_blocked"] is True


def test_actor_provided_not_authoritative() -> None:
    route = build_route(["PRODUCTION_SOURCE_CHANGE"], patch_digest=DIGEST, repository="org/repo")
    forged = actor_provided_receipt(binding=_binding())
    bundle = run_evidence_bus(
        binding=_binding(),
        route=route,
        extra_receipts=[forged],
        adapter_kwargs={"P1": {"verdict": {"passed": True}}},
    )
    actor_items = [
        item
        for item in bundle["receipts"]
        if item.get("trust_class") == TRUST_ACTOR_PROVIDED
        or (isinstance(item.get("producer"), dict) and item["producer"].get("trust_class") == TRUST_ACTOR_PROVIDED)
    ]
    assert actor_items
    for item in actor_items:
        assert item.get("authoritative") is False
        assert item.get("can_authorize") is False


def test_optional_provider_failure_does_not_invent_pass() -> None:
    classes = classify_change_classes(changed_files=["src/a.py", "requirements.txt"])
    route = build_route(classes, patch_digest=DIGEST, repository="org/repo")
    bundle = run_evidence_bus(
        binding=_binding(),
        route=route,
        adapter_kwargs={"P1": {"verdict": {"passed": True}}},
    )
    # optional dependency provider is unbound in registry -> missing optional, not required
    assert "dependency_if_configured" not in bundle["required_provider_failures"]
    assert bundle.get("missing_providers") is not None
