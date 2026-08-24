"""Patch proposal finalize immutability."""

from __future__ import annotations

from datetime import datetime, timezone

from agent_shared.models.transaction.proposal import PatchProposal


class ProposalImmutableError(RuntimeError):
    """Raised when a finalized proposal is mutated."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def finalize_proposal(proposal: PatchProposal, *, finalized_at: str | None = None) -> PatchProposal:
    if proposal.finalized:
        return proposal
    stamp = finalized_at or utc_now()
    return proposal.model_copy(update={"finalized": True, "finalized_at": stamp})


def assert_mutable(proposal: PatchProposal) -> None:
    if proposal.finalized:
        raise ProposalImmutableError("patch_proposal.v1 is immutable after finalize")


def replace_unfinalized(proposal: PatchProposal, **updates: object) -> PatchProposal:
    assert_mutable(proposal)
    return proposal.model_copy(update=updates)
