"""Identity principals and attribution triples for software transactions."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PrincipalKind = Literal[
    "HUMAN_INITIATOR",
    "AGENT_WORKER",
    "CONTROL_PLANE",
    "VERIFIER",
    "EVIDENCE_PROVIDER",
]


class IdentityPrincipal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    principal_kind: PrincipalKind
    identity_id: str = Field(min_length=1)
    issuer: str | None = None
    namespace: str | None = None


class CompositeIdentity(BaseModel):
    """ON_BEHALF_OF / EXECUTED_BY / AUTHORIZED_BY. Do not collapse these."""

    model_config = ConfigDict(extra="forbid")

    ON_BEHALF_OF: IdentityPrincipal
    EXECUTED_BY: IdentityPrincipal
    AUTHORIZED_BY: IdentityPrincipal | None = None
