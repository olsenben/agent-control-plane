"""Model role router."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Literal

from agent_control.config import Settings, get_settings
from agent_control.model_health import probe_model

ProviderKind = Literal["gpu", "external", "fallback"]
TierKind = Literal["3080", "2070"]

TIER_3080_ROLES: Final[frozenset[str]] = frozenset({"planner", "reviewer", "fixer", "judge", "rlm"})
TIER_2070_ROLES: Final[frozenset[str]] = frozenset({"worker", "summarizer", "test_writer", "finding_normalizer"})
ALL_ROLES: Final[frozenset[str]] = TIER_3080_ROLES | TIER_2070_ROLES

ROLE_ENDPOINT_ENV: Final[dict[str, tuple[str, str]]] = {
    "planner": ("MODEL_3080_BASE_URL", "MODEL_3080_NAME"),
    "reviewer": ("MODEL_3080_BASE_URL", "MODEL_3080_NAME"),
    "fixer": ("MODEL_3080_BASE_URL", "MODEL_3080_NAME"),
    "judge": ("MODEL_3080_BASE_URL", "MODEL_3080_NAME"),
    "rlm": ("MODEL_3080_BASE_URL", "MODEL_3080_NAME"),
    "worker": ("MODEL_2070_BASE_URL", "MODEL_2070_NAME"),
    "summarizer": ("MODEL_2070_BASE_URL", "MODEL_2070_NAME"),
    "test_writer": ("MODEL_2070_BASE_URL", "MODEL_2070_NAME"),
    "finding_normalizer": ("MODEL_2070_BASE_URL", "MODEL_2070_NAME"),
}


@dataclass(frozen=True)
class EndpointSpec:
    base_url: str
    model: str
    api_key: str = ""


@dataclass(frozen=True)
class TierEndpoints:
    gpu: EndpointSpec
    external: EndpointSpec
    fallback: EndpointSpec


@dataclass(frozen=True)
class ResolvedEndpoint:
    role: str
    tier: TierKind
    provider: ProviderKind
    base_url: str
    model: str
    api_key: str
    primary_provider: ProviderKind

    def as_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "tier": self.tier,
            "provider": self.provider,
            "base_url": self.base_url,
            "model": self.model,
            "primary_provider": self.primary_provider,
        }


def _tier_for_role(role: str) -> TierKind:
    if role in TIER_3080_ROLES:
        return "3080"
    if role in TIER_2070_ROLES:
        return "2070"
    raise ValueError(f"unknown role: {role}")


def _endpoint_spec(base_url: str, model: str, api_key: str = "") -> EndpointSpec:
    return EndpointSpec(base_url=base_url.strip(), model=model.strip(), api_key=api_key.strip())


def tier_endpoints_for(settings: Settings, tier: TierKind) -> TierEndpoints:
    if tier == "3080":
        return TierEndpoints(
            gpu=_endpoint_spec(
                settings.model_3080_base_url,
                settings.model_3080_name,
                settings.model_3080_api_key,
            ),
            external=_endpoint_spec(
                settings.model_3080_external_base_url,
                settings.model_3080_external_name,
                settings.model_3080_external_api_key,
            ),
            fallback=_endpoint_spec(
                settings.model_3080_fallback_base_url,
                settings.model_3080_fallback_name,
                settings.model_3080_fallback_api_key,
            ),
        )
    return TierEndpoints(
        gpu=_endpoint_spec(
            settings.model_2070_base_url,
            settings.model_2070_name,
            settings.model_2070_api_key,
        ),
        external=_endpoint_spec(
            settings.model_2070_external_base_url,
            settings.model_2070_external_name,
            settings.model_2070_external_api_key,
        ),
        fallback=_endpoint_spec(
            settings.model_2070_fallback_base_url,
            settings.model_2070_fallback_name,
            settings.model_2070_fallback_api_key,
        ),
    )


def _pick_primary_provider(role: str, tier: TierEndpoints, settings: Settings) -> ProviderKind:
    if role in settings.external_roles_set() and tier.external.base_url:
        return "external"
    return "gpu"


def _spec_for_provider(tier: TierEndpoints, provider: ProviderKind) -> EndpointSpec:
    if provider == "external":
        return tier.external
    if provider == "fallback":
        return tier.fallback
    return tier.gpu


def resolve_role_primary(role: str, settings: Settings | None = None) -> ResolvedEndpoint:
    if role not in ALL_ROLES:
        raise ValueError(f"unknown role: {role}")
    settings = settings or get_settings()
    tier_name = _tier_for_role(role)
    tier = tier_endpoints_for(settings, tier_name)
    primary_provider = _pick_primary_provider(role, tier, settings)
    spec = _spec_for_provider(tier, primary_provider)
    return ResolvedEndpoint(
        role=role,
        tier=tier_name,
        provider=primary_provider,
        base_url=spec.base_url,
        model=spec.model,
        api_key=spec.api_key,
        primary_provider=primary_provider,
    )


def resolve_role(role: str, settings: Settings | None = None, *, probe: bool = True) -> dict[str, Any]:
    settings = settings or get_settings()
    resolved = resolve_role_primary(role, settings)
    if not resolved.base_url:
        return {**resolved.as_dict(), "status": "skipped", "reason": "endpoint not configured"}

    if not probe:
        return resolved.as_dict()

    timeout = settings.model_health_timeout_seconds
    primary_probe = probe_model(resolved.base_url, timeout, api_key=resolved.api_key or None)
    if primary_probe.get("status") == "ok":
        return {**resolved.as_dict(), **primary_probe, "fallback_used": False}

    result: dict[str, Any] = {
        **resolved.as_dict(),
        **primary_probe,
        "fallback_used": False,
        "primary_error": primary_probe.get("error"),
    }

    tier = tier_endpoints_for(settings, resolved.tier)
    fallback_spec = tier.fallback
    if not settings.model_fallback_enabled or not fallback_spec.base_url:
        result["status"] = primary_probe.get("status", "unreachable")
        return result

    fallback_probe = probe_model(
        fallback_spec.base_url,
        timeout,
        api_key=fallback_spec.api_key or None,
    )
    if fallback_probe.get("status") == "ok":
        result.update(fallback_probe)
        result["provider"] = "fallback"
        result["model"] = fallback_spec.model or result.get("model", "")
        result["base_url"] = fallback_spec.base_url
        result["fallback_used"] = True
        return result

    result["status"] = primary_probe.get("status", "unreachable")
    result["fallback_error"] = fallback_probe.get("error")
    return result


def ping_role(role: str, settings: Settings | None = None) -> dict[str, Any]:
    """Probe the endpoint for a logical role; returns ok or unreachable."""
    return resolve_role(role, settings, probe=True)


def resolve_role_legacy(role: str, settings: Settings | None = None) -> dict[str, str]:
    """Backward-compatible shape for callers expecting base_url/model only."""
    resolved = resolve_role_primary(role, settings)
    return {
        "role": resolved.role,
        "base_url": resolved.base_url,
        "model": resolved.model,
    }
