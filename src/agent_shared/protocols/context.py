"""W1-seam context protocols. W0 freezes only these two signatures.

Do not add retriever, applicability, authorizer, repair, or episode Protocols here.
Those are frozen in the wave that first depends on them.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from agent_shared.models.context_pack_v2 import ContextPackV2
from agent_shared.models.repo_snapshot import RepoSnapshot


class RepositoryEvidenceProvider(Protocol):
    def query(self, snapshot: RepoSnapshot, request: Any) -> list: ...


class ContextBuilderV2(Protocol):
    def build(
        self,
        snapshot: RepoSnapshot,
        task: Any,
        evidence_budget: Any,
        authorized_experience: Sequence[Any] = (),
    ) -> ContextPackV2: ...
