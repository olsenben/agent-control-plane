"""WRAP frozen C. No semantic rewrite of decide_c / admit_proposal."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from agent_control.transaction.admission.frozen_c import (
    ARM_C,
    AUTO_ADMIT,
    CONTROLLER_NAME,
    ESCALATE,
    EV_ALREADY,
    EV_DERIVED,
    EV_NEW,
    FROZEN_C_HASH,
    REJECT,
    admit_proposal as vendored_admit_proposal,
    classify_units as vendored_classify_units,
    decide_c as vendored_decide_c,
)
from agent_shared.hash_utils import canonical_json_hash
from agent_shared.models.transaction.admission import (
    AdmissionEscalation,
    PatchAdmissionDecision,
    PolicyFields,
)
from agent_shared.models.transaction.identity import CompositeIdentity

MODEL_SPECIFIC_CONTROL_LOGIC = "NO"
SCANNER_SPECIFIC_ADMISSION_LOGIC = "NO"


def load_c_functions() -> tuple[Any, Any, Any, str]:
    """Import eval C when present; otherwise use the vendored byte-stable copy."""
    try:
        from maintenance_evals.vexp_w4_exp22 import (
            admit_proposal,
            classify_units,
            decide_c,
        )

        return decide_c, admit_proposal, classify_units, "import"
    except ImportError:
        return (
            vendored_decide_c,
            vendored_admit_proposal,
            vendored_classify_units,
            "vendored",
        )


decide_c, admit_proposal, classify_units, C_LOAD_MODE = load_c_functions()


def wrap_decide_c(
    *,
    units: Sequence[Mapping[str, Any]],
    changed_paths: Sequence[str],
    decision: Mapping[str, Any] | None,
    g0: Sequence[str],
    verification: Mapping[str, Any],
    policy: PolicyFields,
    proposal_id: str,
    patch_digest: str,
    tenant_id: str | None = None,
    org_id: str | None = None,
    repository: str | None = None,
    required_provider_failed: bool = False,
) -> PatchAdmissionDecision:
    """Call frozen decide_c. Required-provider failure is projected as incomplete."""
    verify = dict(verification)
    if required_provider_failed:
        verify["incomplete"] = True
        verify["passed"] = False
    label, reasons, relation, tier = decide_c(
        units=units,
        changed_paths=changed_paths,
        decision=decision,
        g0=g0,
        verification=verify,
    )
    if required_provider_failed and label == AUTO_ADMIT:
        label = ESCALATE
        reasons = ["REQUIRED_PROVIDER_FAILED", *list(reasons)]
    digest = canonical_json_hash(
        {
            "proposal_id": proposal_id,
            "arm": ARM_C,
            "decision": label,
            "reasons": list(reasons),
            "patch_digest": patch_digest,
        }
    )
    return PatchAdmissionDecision(
        proposal_id=proposal_id,
        arm=ARM_C,
        decision=label,  # type: ignore[arg-type]
        reasons=list(reasons),
        risk_tier=tier,  # type: ignore[arg-type]
        scope_relation=relation,  # type: ignore[arg-type]
        evidence_classes=[EV_ALREADY, EV_DERIVED, EV_NEW],
        verification=verify,
        decision_digest=digest,
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        policy_digest=policy.policy_digest,
        admission_implementation_digest=policy.admission_implementation_digest,
        tenant_id=tenant_id,
        org_id=org_id,
        repository=repository,
    )


def make_escalation(
    *,
    escalation_id: str,
    tenant_id: str,
    org_id: str,
    repository: str,
    task_id: str,
    source_sha: str,
    patch_digest: str,
    task_digest: str,
    bundle_id: str,
    bundle_digest: str,
    reasons: Sequence[str],
    policy: PolicyFields,
    risk_classification: str,
    identity: CompositeIdentity,
    proposal_id: str | None = None,
    decision_id: str | None = None,
    created_at: str | None = None,
) -> AdmissionEscalation:
    return AdmissionEscalation(
        escalation_id=escalation_id,
        decision_id=decision_id,
        proposal_id=proposal_id,
        tenant_id=tenant_id,
        org_id=org_id,
        repository=repository,
        task_id=task_id,
        source_sha=source_sha,
        patch_digest=patch_digest,
        task={"task_id": task_id, "task_digest": task_digest},
        evidence={"bundle_id": bundle_id, "bundle_digest": bundle_digest},
        reasons=list(reasons) or ["ESCALATE"],
        policy=policy,
        risk_classification=risk_classification,  # type: ignore[arg-type]
        identity=identity,
        created_at=created_at,
    )


__all__ = [
    "ARM_C",
    "AUTO_ADMIT",
    "CONTROLLER_NAME",
    "C_LOAD_MODE",
    "ESCALATE",
    "FROZEN_C_HASH",
    "MODEL_SPECIFIC_CONTROL_LOGIC",
    "REJECT",
    "SCANNER_SPECIFIC_ADMISSION_LOGIC",
    "admit_proposal",
    "classify_units",
    "decide_c",
    "load_c_functions",
    "make_escalation",
    "wrap_decide_c",
]
