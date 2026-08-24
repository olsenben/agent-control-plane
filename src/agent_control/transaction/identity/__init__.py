"""Identity helpers. Model identity is attribution metadata, not a C branch."""

from __future__ import annotations

from agent_control.transaction.identity.credentials import worker_credential_assertion
from agent_shared.models.transaction.identity import (
    CompositeIdentity,
    IdentityPrincipal,
    PrincipalKind,
)

CONTROL_PLANE_ISSUER = "authoritative_control_plane"
FIXTURE_ACTOR_ID = "fixture_deterministic"
FIXTURE_ACTOR_ENGINE = "deterministic_fixture_actor"


def principal(
    kind: PrincipalKind,
    identity_id: str,
    *,
    issuer: str | None = None,
    namespace: str | None = None,
) -> IdentityPrincipal:
    return IdentityPrincipal(
        principal_kind=kind,
        identity_id=identity_id,
        issuer=issuer,
        namespace=namespace,
    )


def human_initiator(identity_id: str, *, issuer: str | None = "gitea") -> IdentityPrincipal:
    return principal("HUMAN_INITIATOR", identity_id, issuer=issuer)


def agent_worker(identity_id: str, *, issuer: str | None = "ct104") -> IdentityPrincipal:
    return principal("AGENT_WORKER", identity_id, issuer=issuer)


def control_plane(identity_id: str = CONTROL_PLANE_ISSUER) -> IdentityPrincipal:
    return principal("CONTROL_PLANE", identity_id, issuer=CONTROL_PLANE_ISSUER)


def verifier(identity_id: str, *, issuer: str | None = "ct102") -> IdentityPrincipal:
    return principal("VERIFIER", identity_id, issuer=issuer)


def evidence_provider(identity_id: str, *, issuer: str | None = "control_plane") -> IdentityPrincipal:
    return principal("EVIDENCE_PROVIDER", identity_id, issuer=issuer)


def attribution(
    *,
    on_behalf_of: IdentityPrincipal,
    executed_by: IdentityPrincipal,
    authorized_by: IdentityPrincipal | None = None,
) -> CompositeIdentity:
    return CompositeIdentity(
        ON_BEHALF_OF=on_behalf_of,
        EXECUTED_BY=executed_by,
        AUTHORIZED_BY=authorized_by,
    )


def fixture_actor_identity(*, run_id: str = "fixture-run") -> IdentityPrincipal:
    """Deterministic fixture actor. Not a model router."""
    return agent_worker(f"{FIXTURE_ACTOR_ID}:{run_id}", issuer="fixture")


def fixture_worker_identity() -> IdentityPrincipal:
    return agent_worker("agentworker", issuer="ct104")


__all__ = [
    "CONTROL_PLANE_ISSUER",
    "FIXTURE_ACTOR_ENGINE",
    "FIXTURE_ACTOR_ID",
    "agent_worker",
    "attribution",
    "control_plane",
    "evidence_provider",
    "fixture_actor_identity",
    "fixture_worker_identity",
    "human_initiator",
    "principal",
    "verifier",
    "worker_credential_assertion",
]
