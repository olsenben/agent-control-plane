"""Authorization decision with separate predicates (V6 T05)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

DecisionOutcome = Literal["allow", "deny"]


class PredicateResult(BaseModel):
    allowed: bool
    reason: str = ""
    detail: dict[str, Any] = Field(default_factory=dict)


class AuthorizationDecision(BaseModel):
    schema_version: str = "authorization_decision.v1"
    invoker_check: PredicateResult
    approver_check: PredicateResult
    acting_identity_check: PredicateResult
    policy_check: PredicateResult
    approval_scope: PredicateResult
    source_sha: str = ""
    policy_source_sha: str = ""
    checked_at: str
    decision: DecisionOutcome
    command_kind: str = ""
    project: str = ""
    run_id: str | None = None
    session_id: str | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def evaluate_authorization(
    *,
    command_kind: str,
    project: str,
    invoker_login: str,
    invoker_can_read: bool,
    invoker_is_approver: bool,
    approver_login: str | None,
    acting_identity: str,
    bot_can_write: bool,
    policy_permits: bool,
    policy_reason: str = "",
    approval_valid: bool = True,
    approval_reason: str = "",
    source_sha: str = "",
    policy_source_sha: str = "",
    require_approver: bool = False,
    require_bot_write: bool = False,
    approver_is_authority: bool | None = None,
    run_id: str | None = None,
    session_id: str | None = None,
) -> AuthorizationDecision:
    """Evaluate separate predicates; overall allow only if all required pass.

    Command matrix (plan):
    - inspect/review/plan: invoker can read
    - request fix: invoker role (approver list or read — policy-selected)
    - approve fix: owner/configured approver
    - publish: bot has write + recorded approver still authoritative
    """
    kind = (command_kind or "").lower()
    invoker_ok = PredicateResult(
        allowed=invoker_can_read,
        reason="invoker has repo read" if invoker_can_read else "invoker lacks repo read",
        detail={"login": invoker_login},
    )
    if kind in ("approve", "reject"):
        invoker_ok = PredicateResult(
            allowed=invoker_is_approver,
            reason="invoker is approval authority" if invoker_is_approver else "invoker is not approver",
            detail={"login": invoker_login},
        )

    if require_approver:
        authority = (
            invoker_is_approver
            if kind in ("approve", "reject")
            else (approver_is_authority if approver_is_authority is not None else bool(approver_login))
        )
        allowed = bool(approver_login) and bool(authority)
        if not approver_login:
            reason = "approver missing"
        elif not authority:
            reason = "approver is not approval authority"
        else:
            reason = "approver authorized"
        approver_ok = PredicateResult(
            allowed=allowed,
            reason=reason,
            detail={"login": approver_login},
        )
    else:
        approver_ok = PredicateResult(allowed=True, reason="approver not required for this command")

    if require_bot_write:
        acting_ok = PredicateResult(
            allowed=bot_can_write,
            reason="agent-bot has write" if bot_can_write else "agent-bot lacks write",
            detail={"acting_identity": acting_identity},
        )
    else:
        acting_ok = PredicateResult(
            allowed=True,
            reason="mutation not required",
            detail={"acting_identity": acting_identity},
        )

    policy_ok = PredicateResult(
        allowed=policy_permits,
        reason=policy_reason or ("policy permits" if policy_permits else "policy denied"),
    )
    scope_ok = PredicateResult(
        allowed=approval_valid,
        reason=approval_reason or ("approval scope valid" if approval_valid else "approval invalid"),
        detail={"source_sha": source_sha},
    )

    decision: DecisionOutcome = (
        "allow"
        if (
            invoker_ok.allowed
            and approver_ok.allowed
            and acting_ok.allowed
            and policy_ok.allowed
            and scope_ok.allowed
        )
        else "deny"
    )
    return AuthorizationDecision(
        invoker_check=invoker_ok,
        approver_check=approver_ok,
        acting_identity_check=acting_ok,
        policy_check=policy_ok,
        approval_scope=scope_ok,
        source_sha=source_sha,
        policy_source_sha=policy_source_sha,
        checked_at=_now(),
        decision=decision,
        command_kind=kind,
        project=project,
        run_id=run_id,
        session_id=session_id,
    )
