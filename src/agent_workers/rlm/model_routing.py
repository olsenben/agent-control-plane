"""Worker-side model endpoint resolution (Slice 6D.1).

Does not import agent_control. Reads MODEL_* env vars directly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

ProviderKind = Literal["gpu", "external"]


@dataclass(frozen=True)
class WorkerResolvedEndpoint:
    provider: ProviderKind
    base_url: str
    model: str
    api_key: str = ""

    @property
    def tier(self) -> str:
        return "3080"


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def external_roles_set() -> frozenset[str]:
    raw = _env("MODEL_EXTERNAL_ROLES")
    if not raw:
        return frozenset()
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def resolve_rlm_gpu_endpoint() -> WorkerResolvedEndpoint:
    return WorkerResolvedEndpoint(
        provider="gpu",
        base_url=_env("MODEL_3080_BASE_URL"),
        model=_env("MODEL_3080_NAME"),
        api_key=_env("MODEL_3080_API_KEY"),
    )


def resolve_rlm_external_endpoint() -> WorkerResolvedEndpoint | None:
    if "rlm" not in external_roles_set():
        return None
    base_url = _env("MODEL_3080_EXTERNAL_BASE_URL")
    if not base_url:
        return None
    return WorkerResolvedEndpoint(
        provider="external",
        base_url=base_url,
        model=_env("MODEL_3080_EXTERNAL_NAME"),
        api_key=_env("MODEL_3080_EXTERNAL_API_KEY"),
    )


def to_control_plane_endpoint(endpoint: WorkerResolvedEndpoint):
    """Adapt worker endpoint for StructuredOutputClient (agent_control ResolvedEndpoint)."""
    from agent_control.model_router import ResolvedEndpoint

    return ResolvedEndpoint(
        role="rlm",
        tier="3080",
        provider=endpoint.provider,
        base_url=endpoint.base_url,
        model=endpoint.model,
        api_key=endpoint.api_key,
        primary_provider=endpoint.provider,
    )
