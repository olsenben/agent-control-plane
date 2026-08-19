"""Exact-SHA repository snapshot identity (VExp W0-A).

``snapshot_id`` is a stable hex digest of ``(repository_id, target_sha)`` only.
Checkout location (``workspace_path``) and derived index materialization
(``index_generation``) are not part of identity.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_shared.hash_utils import canonical_json_hash

SourceKind = Literal["gitea", "eval"]


def compute_snapshot_id(repository_id: str, target_sha: str) -> str:
    """Return the hex digest of ``(repository_id, target_sha)`` only."""
    return canonical_json_hash({"repository_id": repository_id, "target_sha": target_sha})


class RepoSnapshot(BaseModel):
    """Frozen exact-SHA snapshot. Identity is repository + target SHA."""

    model_config = ConfigDict(frozen=True)

    repository_id: str = Field(min_length=1)
    repository_url_or_key: str = Field(min_length=1)
    target_sha: str = Field(min_length=1)
    workspace_path: str
    lineage_id: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_kind: SourceKind
    index_generation: str = "0"
    snapshot_id: str = ""

    @model_validator(mode="before")
    @classmethod
    def _bind_snapshot_id(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        repository_id = data.get("repository_id")
        target_sha = data.get("target_sha")
        if repository_id is None or target_sha is None:
            return data
        digest = compute_snapshot_id(str(repository_id), str(target_sha))
        provided = data.get("snapshot_id")
        if provided not in (None, "", digest):
            raise ValueError(
                "snapshot_id must be the digest of (repository_id, target_sha) only"
            )
        bound = dict(data)
        bound["snapshot_id"] = digest
        return bound
