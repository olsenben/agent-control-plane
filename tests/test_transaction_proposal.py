"""Patch proposal finalize immutability."""

from __future__ import annotations

import pytest

from agent_control.transaction.identity import fixture_actor_identity, fixture_worker_identity
from agent_control.transaction.proposal import (
    ProposalImmutableError,
    finalize_proposal,
    replace_unfinalized,
)
from agent_shared.models.transaction.proposal import PatchProposal


def _proposal(**updates: object) -> PatchProposal:
    body = {
        "session_id": "s1",
        "proposal_id": "p1",
        "repo": "org/repo",
        "tenant_id": "t",
        "org_id": "o",
        "task_id": "task-1",
        "source_sha": "abc1234",
        "source_tree_digest": "a" * 64,
        "patch_digest": "b" * 64,
        "changed_files": ["src/pkg/core.py"],
        "actor_identity": fixture_actor_identity(),
        "worker_identity": fixture_worker_identity(),
        "created_at": "2026-08-24T00:00:00+00:00",
        "raw_patch_location": "inbox/p1.diff",
        "raw_patch_digest": "c" * 64,
        "finalized": False,
    }
    body.update(updates)
    return PatchProposal.model_validate(body)


def test_finalize_then_immutable() -> None:
    proposal = finalize_proposal(_proposal(), finalized_at="2026-08-24T01:00:00+00:00")
    assert proposal.finalized is True
    assert proposal.immutable_after_finalize is True
    with pytest.raises(ProposalImmutableError):
        replace_unfinalized(proposal, patch_digest="d" * 64)


def test_unfinalized_can_change_digest() -> None:
    updated = replace_unfinalized(_proposal(), patch_digest="d" * 64)
    assert updated.patch_digest == "d" * 64
    assert updated.finalized is False
