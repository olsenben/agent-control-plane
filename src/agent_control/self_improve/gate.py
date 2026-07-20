"""In-prod self-edit denial and proposal eligibility for gated paths."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from agent_control.self_improve.paths import (
    PRODUCTION_DEPLOY_ROOTS,
    classify_paths,
    is_gated_self_improve_path,
)

REASON_IN_PROD = "in_prod_self_edit_denied"
REASON_NOT_GATED = "path_not_self_improve_gated"
REASON_EMPTY = "no_paths"
REASON_OK_PROPOSE = "propose_as_pr_only"
REASON_OK_NON_PROD = "non_prod_workspace"


@dataclass
class SelfImproveDecision:
    policy_decision: str  # allow | deny
    reason: str | None = None
    gated_paths: list[str] = field(default_factory=list)
    other_paths: list[str] = field(default_factory=list)
    in_prod_target: bool = False
    risk_tags: list[str] = field(default_factory=list)


def normalize_deploy_root(path: Path | str) -> str:
    raw = str(path).replace("\\", "/").rstrip("/")
    return raw


def is_production_deploy_root(target_root: Path | str) -> bool:
    """True when target is a live CT103/CT104 app checkout (not a temp clone)."""
    norm = normalize_deploy_root(target_root)
    for marker in PRODUCTION_DEPLOY_ROOTS:
        if norm == marker or norm.endswith(marker):
            return True
    # Explicit live marker file (optional operator pin)
    try:
        p = Path(target_root)
        if (p / ".agent-control-plane-live").is_file():
            return True
    except OSError:
        pass
    return False


def evaluate_in_prod_self_edit(
    target_root: Path | str,
    paths: list[str],
) -> SelfImproveDecision:
    """Deny writing gated prompt/workflow/policy paths into a live deploy root."""
    classified = classify_paths(paths)
    gated = classified["gated"]
    other = classified["other"]
    in_prod = is_production_deploy_root(target_root)
    if not paths or (not gated and not other):
        return SelfImproveDecision(
            policy_decision="deny",
            reason=REASON_EMPTY,
            gated_paths=gated,
            other_paths=other,
            in_prod_target=in_prod,
            risk_tags=["self_improve"],
        )
    if gated and in_prod:
        return SelfImproveDecision(
            policy_decision="deny",
            reason=REASON_IN_PROD,
            gated_paths=gated,
            other_paths=other,
            in_prod_target=True,
            risk_tags=["self_improve", "in_prod_self_edit"],
        )
    return SelfImproveDecision(
        policy_decision="allow",
        reason=REASON_OK_NON_PROD if not in_prod else None,
        gated_paths=gated,
        other_paths=other,
        in_prod_target=in_prod,
        risk_tags=["self_improve"],
    )


def evaluate_proposal_eligibility(paths: list[str]) -> SelfImproveDecision:
    """Proposal must touch at least one gated path and only gated paths."""
    classified = classify_paths(paths)
    gated = classified["gated"]
    other = classified["other"]
    if not gated and not other:
        return SelfImproveDecision(
            policy_decision="deny",
            reason=REASON_EMPTY,
            risk_tags=["self_improve"],
        )
    if other:
        return SelfImproveDecision(
            policy_decision="deny",
            reason=REASON_NOT_GATED,
            gated_paths=gated,
            other_paths=other,
            risk_tags=["self_improve"],
        )
    return SelfImproveDecision(
        policy_decision="allow",
        reason=REASON_OK_PROPOSE,
        gated_paths=gated,
        other_paths=[],
        risk_tags=["self_improve"],
    )


def decision_as_dict(d: SelfImproveDecision) -> dict:
    return {
        "policy_decision": d.policy_decision,
        "reason": d.reason,
        "gated_paths": list(d.gated_paths),
        "other_paths": list(d.other_paths),
        "in_prod_target": d.in_prod_target,
        "risk_tags": list(d.risk_tags),
        "in_prod_self_edit_forbidden": True,
        "mutation_channel": "gitea_pr_only",
    }


__all__ = [
    "REASON_IN_PROD",
    "REASON_NOT_GATED",
    "REASON_EMPTY",
    "REASON_OK_PROPOSE",
    "SelfImproveDecision",
    "decision_as_dict",
    "evaluate_in_prod_self_edit",
    "evaluate_proposal_eligibility",
    "is_gated_self_improve_path",
    "is_production_deploy_root",
]
