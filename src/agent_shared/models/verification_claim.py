"""Session-scoped verification claim (Slice 5.6)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

VerificationStatus = Literal["requested", "passed", "failed", "missing"]
VerificationSource = Literal["ct102", "aci", "gitea_workflow", "human", "none"]


class VerificationClaim(BaseModel):
    """Machine-recorded verification evidence for an agent session.

    Reasoning / model prose alone cannot set status=passed.
    """

    schema_version: str = "verification_claim.v1"
    session_id: str
    run_id: str
    repo: str
    claim: str
    scope_commit_sha: str
    source: VerificationSource = "none"
    status: VerificationStatus
    command_id: str | None = None
    artifact: str = ""
    limitations: str = ""
    verdict_revision: int | None = None
    created_at: str
    updated_at: str
    artifact_digest: str = ""
    risk_tags: list[str] = Field(default_factory=list)
