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
