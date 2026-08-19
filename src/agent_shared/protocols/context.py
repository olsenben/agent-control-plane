"""W1-seam context protocols.

Do not add retriever, applicability, authorizer, repair, episode, or
state_predicate Protocols here. Those are frozen in the wave that first
depends on them.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from agent_shared.models.evidence_query import (
    ContextBuildResult,
    ContextTaskSpec,
    EvidenceBudget,
    EvidenceQuery,
    ProviderResult,
)
from agent_shared.models.repo_snapshot import RepoSnapshot


class RepositoryEvidenceProvider(Protocol):
    def query(self, snapshot: RepoSnapshot, request: EvidenceQuery) -> ProviderResult: ...


class ContextBuilderV2(Protocol):
    def build(
        self,
        snapshot: RepoSnapshot,
        task: ContextTaskSpec,
        evidence_budget: EvidenceBudget,
        authorized_experience: Sequence[object] = (),
    ) -> ContextBuildResult: ...
