"""PDP input-completeness preflight. READY vs INCOMPLETE only. Does not retune C."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from agent_control.transaction.policy_bundle import (
    G0_LOAD_FAILED,
    G0InputBinding,
)
from agent_shared.hash_utils import canonical_json_hash
from agent_shared.models.transaction.admission import PatchAdmissionDecision, PolicyFields
from agent_shared.models.transaction.preflight import TransactionPreflight

DETERMINISTIC_PREFLIGHT_REVISIT = "YES"
PREFLIGHT_READY = "READY"
PREFLIGHT_INCOMPLETE = "INCOMPLETE"
PDP_INPUT_INCOMPLETE = "PDP_INPUT_INCOMPLETE"
POLICY_UNAVAILABLE = "POLICY_UNAVAILABLE"


def _digest_ok(value: str | None) -> bool:
    if not value or len(value) != 64:
        return False
    return all(ch in "0123456789abcdef" for ch in value)


def evaluate_transaction_preflight(
    *,
    changed_paths: Sequence[str] | None,
    units: Sequence[Mapping[str, Any]] | None,
    verification: Mapping[str, Any] | None,
    policy: PolicyFields | None,
    g0: G0InputBinding | None,
    proposal_id: str | None,
    patch_digest: str | None,
    decision: Mapping[str, Any] | None = None,
    policy_bundle_digest: str | None = None,
) -> TransactionPreflight:
    """Gate C invocation on PDP input completeness, not actor context."""
    del decision  # present for the contract; not an actor-context check
    missing: list[str] = []
    if not proposal_id:
        missing.append("proposal_id")
    if not _digest_ok(patch_digest):
        missing.append("patch_digest")
    if units is None:
        missing.append("units")
    if changed_paths is None:
        missing.append("changed_paths")
    if not isinstance(verification, Mapping):
        missing.append("verification")
    policy_missing = policy is None
    if policy_missing:
        missing.append("policy")

    g0_state = g0.state if g0 is not None else None
    if g0 is None or g0.fail_closed:
        missing.append("g0_input")

    incomplete_reason: str | None = None
    if missing:
        policy_unavailable = policy_missing or (g0 is not None and g0.state == G0_LOAD_FAILED)
        incomplete_reason = POLICY_UNAVAILABLE if policy_unavailable else PDP_INPUT_INCOMPLETE
        status = PREFLIGHT_INCOMPLETE
    else:
        status = PREFLIGHT_READY

    return TransactionPreflight(
        status=status,  # type: ignore[arg-type]
        missing_inputs=missing,
        incomplete_reason=incomplete_reason,  # type: ignore[arg-type]
        g0_input_state=g0_state,  # type: ignore[arg-type]
        policy_bundle_digest=policy_bundle_digest if _digest_ok(policy_bundle_digest) else None,
        deterministic_preflight_revisit=DETERMINISTIC_PREFLIGHT_REVISIT,  # type: ignore[arg-type]
    )


def incomplete_admission_decision(
    *,
    proposal_id: str,
    patch_digest: str,
    policy: PolicyFields | None,
    reason: str,
    g0_input_state: str | None,
    policy_bundle_digest: str | None,
    verification: Mapping[str, Any] | None = None,
) -> PatchAdmissionDecision:
    """Reject without calling C. Mint zero capabilities."""
    from agent_control.transaction.admission import ARM_C, FROZEN_C_HASH, REJECT

    digest = canonical_json_hash(
        {
            "proposal_id": proposal_id or "unknown",
            "arm": ARM_C,
            "decision": REJECT,
            "reasons": [reason],
            "patch_digest": patch_digest if _digest_ok(patch_digest) else "0" * 64,
            "preflight": PREFLIGHT_INCOMPLETE,
        }
    )
    fallback_digest = "0" * 64
    return PatchAdmissionDecision(
        proposal_id=proposal_id or "unknown",
        arm=ARM_C,
        decision=REJECT,  # type: ignore[arg-type]
        reasons=[reason],
        risk_tier="UNKNOWN",
        scope_relation="SELECTED_SCOPE_UNAVAILABLE",
        evidence_classes=[],
        verification=dict(verification or {}),
        decision_digest=digest,
        policy_id=policy.policy_id if policy is not None else "unavailable",
        policy_version=policy.policy_version if policy is not None else "unavailable",
        policy_digest=policy.policy_digest if policy is not None else fallback_digest,
        admission_implementation_digest=(
            policy.admission_implementation_digest if policy is not None else FROZEN_C_HASH
        ),
        g0_input_state=g0_input_state,
        policy_bundle_digest=policy_bundle_digest if _digest_ok(policy_bundle_digest) else None,
    )
