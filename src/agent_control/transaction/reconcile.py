"""Deterministic Gitea reconcile. Inspect expected effect; never blindly repeat."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from agent_control.transaction.retry import (
    AMBIGUOUS_EXTERNAL_EFFECT,
    PERMANENT,
    RECONCILE_BEFORE_RETRY,
    TRANSIENT,
    FailureClassification,
    classify_exception,
)

ReconcileStatus = Literal[
    "ALREADY_APPLIED",
    "NOT_APPLIED",
    "CONFLICT",
    "STILL_AMBIGUOUS",
]

NextSafeAction = Literal[
    "NO_RETRY",
    "RETRY_PUSH",
    "RETRY_PR_OPEN",
    "RECONCILE_BEFORE_RETRY",
    "OPERATOR_INTERVENTION",
]


@dataclass(frozen=True)
class ExpectedPublishEffect:
    repo: str
    branch: str
    commit_sha: str
    transaction_id: str | None = None
    run_id: str | None = None
    bundle_id: str | None = None
    marker: str | None = None


@dataclass(frozen=True)
class ObservedGitea:
    branch_exists: bool | None = None
    branch_sha: str | None = None
    prs: tuple[dict[str, Any], ...] = ()
    read_error: str | None = None
    source_sha: str | None = None


@dataclass(frozen=True)
class ReconcileDecision:
    status: ReconcileStatus
    next_action: NextSafeAction
    retry_class: str
    already_applied: bool
    reason: str
    matched_pr: dict[str, Any] | None = None
    detail: dict[str, Any] = field(default_factory=dict)


def transaction_marker(*, run_id: str, bundle_id: str | None = None) -> str:
    if bundle_id:
        return f"agent-run-id:{run_id} bundle-id:{bundle_id}"
    return f"agent-run-id:{run_id}"


def _pr_has_marker(pr: dict[str, Any], marker: str | None, run_id: str | None) -> bool:
    body = str(pr.get("body") or "")
    title = str(pr.get("title") or "")
    blob = f"{body}\n{title}"
    if marker and marker in blob:
        return True
    if run_id and f"agent-run-id:{run_id}" in blob:
        return True
    if run_id and str(pr.get("head", {}).get("ref") or "").endswith(run_id):
        return True
    return False


def inspect_expected_effect(
    expected: ExpectedPublishEffect,
    observed: ObservedGitea,
) -> ReconcileDecision:
    """Return ALREADY_APPLIED or the next safe action. Never 'just retry push'."""
    if observed.read_error:
        return ReconcileDecision(
            status="STILL_AMBIGUOUS",
            next_action="RECONCILE_BEFORE_RETRY",
            retry_class=RECONCILE_BEFORE_RETRY,
            already_applied=False,
            reason="gitea_read_failed",
            detail={"read_error": observed.read_error},
        )
    marker = expected.marker or (
        transaction_marker(run_id=expected.run_id, bundle_id=expected.bundle_id)
        if expected.run_id
        else None
    )
    matching_prs = [
        pr
        for pr in observed.prs
        if _pr_has_marker(pr, marker, expected.run_id)
        or str((pr.get("head") or {}).get("ref") or "") == expected.branch
    ]
    sha_matches = bool(
        observed.branch_exists
        and observed.branch_sha
        and observed.branch_sha == expected.commit_sha
    )
    if sha_matches:
        matched = matching_prs[0] if matching_prs else None
        return ReconcileDecision(
            status="ALREADY_APPLIED",
            next_action="NO_RETRY" if matched else "RETRY_PR_OPEN",
            retry_class=AMBIGUOUS_EXTERNAL_EFFECT,
            already_applied=True,
            reason="branch_commit_matches_expected",
            matched_pr=matched,
        )
    if matching_prs:
        head_sha = str(
            ((matching_prs[0].get("head") or {}).get("sha"))
            or ((matching_prs[0].get("head") or {}).get("id"))
            or ""
        )
        if head_sha and expected.commit_sha and head_sha == expected.commit_sha:
            return ReconcileDecision(
                status="ALREADY_APPLIED",
                next_action="NO_RETRY",
                retry_class=AMBIGUOUS_EXTERNAL_EFFECT,
                already_applied=True,
                reason="pr_head_matches_expected",
                matched_pr=matching_prs[0],
            )
        return ReconcileDecision(
            status="CONFLICT",
            next_action="OPERATOR_INTERVENTION",
            retry_class=PERMANENT,
            already_applied=False,
            reason="pr_exists_with_unexpected_head",
            matched_pr=matching_prs[0],
            detail={"observed_head": head_sha},
        )
    if observed.branch_exists and observed.branch_sha and observed.branch_sha != expected.commit_sha:
        return ReconcileDecision(
            status="CONFLICT",
            next_action="OPERATOR_INTERVENTION",
            retry_class=PERMANENT,
            already_applied=False,
            reason="branch_sha_mismatch",
            detail={"observed_sha": observed.branch_sha},
        )
    if observed.branch_exists is False and not matching_prs:
        return ReconcileDecision(
            status="NOT_APPLIED",
            next_action="RETRY_PUSH",
            retry_class=TRANSIENT,
            already_applied=False,
            reason="branch_and_pr_absent",
        )
    return ReconcileDecision(
        status="STILL_AMBIGUOUS",
        next_action="RECONCILE_BEFORE_RETRY",
        retry_class=RECONCILE_BEFORE_RETRY,
        already_applied=False,
        reason="insufficient_observation",
    )


def classify_gitea_failure(
    exc: BaseException,
    *,
    request_sent: bool,
) -> FailureClassification:
    return classify_exception(exc, request_sent=request_sent)


def observe_from_client(
    client: Any,
    expected: ExpectedPublishEffect,
) -> ObservedGitea:
    """Read-only Gitea inspection. Never mutates. Does not log credentials."""
    if "/" not in expected.repo:
        return ObservedGitea(read_error="invalid_repo")
    owner, name = expected.repo.split("/", 1)
    try:
        sha = client.get_branch_sha(owner, name, expected.branch)
        prs = []
        if hasattr(client, "list_pull_requests"):
            prs = client.list_pull_requests(owner, name, head=expected.branch, state="open") or []
        return ObservedGitea(
            branch_exists=True,
            branch_sha=str(sha or "") or None,
            prs=tuple(prs) if isinstance(prs, list) else (),
        )
    except Exception as exc:  # noqa: BLE001
        status = getattr(exc, "status_code", None)
        response = getattr(exc, "response", None)
        if status is None:
            status = getattr(response, "status_code", None)
        if status == 404:
            prs: list[dict[str, Any]] = []
            try:
                if hasattr(client, "list_pull_requests"):
                    prs = client.list_pull_requests(
                        owner, name, head=expected.branch, state="open"
                    ) or []
            except Exception:  # noqa: BLE001
                prs = []
            return ObservedGitea(branch_exists=False, branch_sha=None, prs=tuple(prs))
        return ObservedGitea(read_error=type(exc).__name__)


ALREADY_CONVERGED = "ALREADY_CONVERGED"
SAFE_TO_CONTINUE = "SAFE_TO_CONTINUE"
WAITING_EXTERNAL = "WAITING_EXTERNAL"
RETRY_READ = "RETRY_READ"
RECREATE_MISSING_PR = "RECREATE_MISSING_PR"
CANCELLED_NO_EFFECT = "CANCELLED_NO_EFFECT"
CANCEL_TOO_LATE = "CANCEL_TOO_LATE"
SOURCE_DRIFT = "SOURCE_DRIFT"
EXTERNAL_STATE_CONFLICT = "EXTERNAL_STATE_CONFLICT"
MANUAL_INTERVENTION_REQUIRED = "MANUAL_INTERVENTION_REQUIRED"

TransactionReconcileStatus = Literal[
    "ALREADY_CONVERGED",
    "SAFE_TO_CONTINUE",
    "WAITING_EXTERNAL",
    "RETRY_READ",
    "RECREATE_MISSING_PR",
    "CANCELLED_NO_EFFECT",
    "CANCEL_TOO_LATE",
    "SOURCE_DRIFT",
    "EXTERNAL_STATE_CONFLICT",
    "MANUAL_INTERVENTION_REQUIRED",
]

AUTHORIZED_PARTIAL_EFFECT = "AUTHORIZED_PARTIAL_EFFECT"


@dataclass(frozen=True)
class TransactionReconcileResult:
    status: TransactionReconcileStatus
    inspect: ReconcileDecision | None = None
    reason: str = ""
    cancelled: bool = False
    capability_lifecycle: str | None = None
    barrier_kinds: tuple[str, ...] = ()
    publish_effect_id: str | None = None
    matched_pr: dict[str, Any] | None = None
    detail: dict[str, Any] = field(default_factory=dict)


def reconcile_transaction(
    state_root: Any,
    transaction_id: str,
    *,
    gitea_client: Any = None,
    cancelled: bool = False,
    observed: ObservedGitea | None = None,
) -> TransactionReconcileResult:
    """Typed reconcile over durable intent, capability, barriers, and ObservedGitea.

    Never pushes a different patch. RECREATE_MISSING_PR may only open the exact intended PR.
    """
    from pathlib import Path

    from agent_control.publish.state import find_intent_by_transaction_id
    from agent_control.transaction.barriers import (
        KIND_CANCELLED,
        barrier_kinds,
    )
    from agent_control.transaction.capability import FilesystemCapabilityStore, lifecycle_of
    from agent_control.transaction.retry import MANUAL_INTERVENTION, PERMANENT

    root = Path(state_root)
    intent = find_intent_by_transaction_id(root, transaction_id)
    run_id = intent.run_id if intent is not None else transaction_id
    kinds = frozenset(barrier_kinds(root, run_id))
    cancelled_flag = bool(cancelled) or KIND_CANCELLED in kinds
    cap_lifecycle: str | None = None
    if intent is not None and intent.capability_id:
        stored = FilesystemCapabilityStore(root / "transaction" / "capabilities").get(
            intent.capability_id
        )
        if stored is not None:
            cap_lifecycle = lifecycle_of(stored)

    if intent is None:
        if cancelled_flag:
            return TransactionReconcileResult(
                status="CANCELLED_NO_EFFECT",
                reason="no_intent_cancelled",
                cancelled=True,
                capability_lifecycle=cap_lifecycle,
                barrier_kinds=tuple(sorted(kinds)),
            )
        if gitea_client is None and observed is None:
            return TransactionReconcileResult(
                status="WAITING_EXTERNAL",
                reason="no_intent_insufficient_observation",
                cancelled=False,
                capability_lifecycle=cap_lifecycle,
                barrier_kinds=tuple(sorted(kinds)),
            )
        return TransactionReconcileResult(
            status="MANUAL_INTERVENTION_REQUIRED",
            reason="no_durable_intent",
            cancelled=False,
            capability_lifecycle=cap_lifecycle,
            barrier_kinds=tuple(sorted(kinds)),
            detail={"retry_class": MANUAL_INTERVENTION},
        )

    expected = ExpectedPublishEffect(
        repo=intent.project,
        branch=intent.agent_branch,
        commit_sha=intent.expected_commit_sha,
        transaction_id=intent.transaction_id or transaction_id,
        run_id=intent.run_id,
        bundle_id=intent.bundle_id,
        marker=transaction_marker(run_id=intent.run_id, bundle_id=intent.bundle_id),
    )
    observed_gitea = observed
    if observed_gitea is None and gitea_client is not None:
        observed_gitea = observe_from_client(gitea_client, expected)
    if observed_gitea is None:
        return TransactionReconcileResult(
            status="WAITING_EXTERNAL",
            reason="insufficient_observation",
            cancelled=cancelled_flag,
            capability_lifecycle=cap_lifecycle,
            barrier_kinds=tuple(sorted(kinds)),
            publish_effect_id=intent.publish_effect_id,
        )

    decision = inspect_expected_effect(expected, observed_gitea)
    base: dict[str, Any] = {
        "cancelled": cancelled_flag,
        "capability_lifecycle": cap_lifecycle,
        "barrier_kinds": tuple(sorted(kinds)),
        "publish_effect_id": intent.publish_effect_id,
        "inspect": decision,
        "matched_pr": decision.matched_pr,
        "reason": decision.reason,
    }
    if observed_gitea.read_error:
        return TransactionReconcileResult(status="RETRY_READ", **base)
    if (
        intent.source_sha
        and observed_gitea.source_sha
        and intent.source_sha != observed_gitea.source_sha
        and decision.status in {"NOT_APPLIED", "STILL_AMBIGUOUS"}
    ):
        return TransactionReconcileResult(status="SOURCE_DRIFT", **base)
    if decision.status == "CONFLICT":
        return TransactionReconcileResult(
            status="EXTERNAL_STATE_CONFLICT",
            detail={"retry_class": PERMANENT, "fail_closed": True},
            **base,
        )
    if decision.status == "ALREADY_APPLIED":
        if decision.matched_pr is not None:
            return TransactionReconcileResult(status="ALREADY_CONVERGED", **base)
        if cancelled_flag:
            return TransactionReconcileResult(
                status="CANCEL_TOO_LATE",
                detail={"authorized_partial_effect": AUTHORIZED_PARTIAL_EFFECT},
                **base,
            )
        return TransactionReconcileResult(status="RECREATE_MISSING_PR", **base)
    if decision.status == "NOT_APPLIED":
        if cancelled_flag:
            return TransactionReconcileResult(status="CANCELLED_NO_EFFECT", **base)
        return TransactionReconcileResult(status="SAFE_TO_CONTINUE", **base)
    if decision.status == "STILL_AMBIGUOUS":
        return TransactionReconcileResult(status="WAITING_EXTERNAL", **base)
    return TransactionReconcileResult(
        status="MANUAL_INTERVENTION_REQUIRED",
        detail={"retry_class": MANUAL_INTERVENTION},
        **base,
    )
