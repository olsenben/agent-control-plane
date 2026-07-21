"""Bounded completion client with failover and attempt budget (V6 T04).

Failure classes:
- transport/timeout/5xx/rate-limit -> gateway retry/fallback
- schema parse failure -> schema repair (caller)
- low-quality valid output -> quality loop (caller)
- policy/data-egress denial -> no external fallback
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import httpx

from agent_control.config import Settings, get_settings
from agent_control.model_egress import evaluate_external_egress
from agent_control.model_route_events import (
    MODEL_ALL_ROUTES_FAILED,
    MODEL_CALL_COMPLETED,
    MODEL_FALLBACK_SELECTED,
    MODEL_ROUTE_ATTEMPTED,
    MODEL_ROUTE_FAILED,
    append_model_route_event,
)
from agent_control.model_router import (
    ResolvedEndpoint,
    resolve_role_primary,
    tier_endpoints_for,
)
from agent_shared.models.model_attempt_budget import AttemptBudgetTracker, budget_from_env
from agent_workers.rlm.completion import chat_completion

logger = logging.getLogger(__name__)


class ModelRouteExhausted(RuntimeError):
    """All permitted model routes failed or budget exhausted."""


@dataclass
class RouteAttempt:
    provider: str
    model: str
    base_url: str
    endpoint_class: str
    data_left_homelab: bool
    retry_number: int
    ok: bool
    error_class: str | None = None
    latency_ms: float | None = None
    token_counts: dict[str, Any] = field(default_factory=dict)


def _error_class(exc: BaseException) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code == 429:
            return "rate_limit"
        if code >= 500:
            return "http_5xx"
        return f"http_{code}"
    if isinstance(exc, httpx.TransportError):
        return "transport"
    return "unknown"


def _request_hash(system_prompt: str, user_prompt: str) -> str:
    digest = hashlib.sha256(f"{system_prompt}\n{user_prompt}".encode("utf-8")).hexdigest()
    return digest[:16]


def gateway_endpoint_for_role(role: str, settings: Settings | None = None) -> ResolvedEndpoint | None:
    """When MODEL_GATEWAY_BASE_URL is set, route through CT103 LiteLLM proxy."""
    settings = settings or get_settings()
    gw = (getattr(settings, "model_gateway_base_url", "") or "").strip()
    if not gw:
        return None
    primary = resolve_role_primary(role, settings)
    model = getattr(settings, "model_gateway_model_map", "") or ""
    # Optional map "planner=primary-generator,worker=context-controller"
    mapped = primary.model
    for part in model.split(","):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        if k.strip() == role:
            mapped = v.strip()
            break
    if not mapped:
        mapped = "primary-generator" if primary.tier == "3080" else "context-controller"
    return ResolvedEndpoint(
        role=role,
        tier=primary.tier,
        provider="gpu",
        base_url=gw,
        model=mapped,
        api_key=(getattr(settings, "model_gateway_api_key", "") or "").strip(),
        primary_provider=primary.primary_provider,
    )


def _candidate_endpoints(
    role: str,
    *,
    project: str,
    settings: Settings,
) -> list[tuple[str, ResolvedEndpoint, bool]]:
    """Return ordered (label, endpoint, data_leaves_homelab) candidates.

    Deterministic context fallback is NOT listed here — callers handle that
    in CT103 application policy when the 2070/context controller is down.
    """
    out: list[tuple[str, ResolvedEndpoint, bool]] = []
    gw = gateway_endpoint_for_role(role, settings)
    if gw is not None:
        out.append(("gateway", gw, False))
        # Gateway owns provider failover; still allow direct fallback only if gateway unset path.
        return out

    primary = resolve_role_primary(role, settings)
    if primary.base_url:
        leaves = primary.provider in ("external", "fallback")
        if leaves:
            decision = evaluate_external_egress(
                project=project, role=role, provider=primary.provider, settings=settings
            )
            if decision.allowed:
                out.append(("primary", primary, True))
        else:
            out.append(("primary", primary, False))

    if not settings.model_fallback_enabled:
        return out

    tier = tier_endpoints_for(settings, primary.tier)
    if tier.fallback.base_url:
        decision = evaluate_external_egress(
            project=project, role=role, provider="fallback", settings=settings
        )
        if decision.allowed:
            fb = ResolvedEndpoint(
                role=role,
                tier=primary.tier,
                provider="fallback",
                base_url=tier.fallback.base_url,
                model=tier.fallback.model or primary.model,
                api_key=tier.fallback.api_key,
                primary_provider=primary.primary_provider,
            )
            out.append(("fallback", fb, True))
    return out


def chat_completion_with_failover(
    role: str,
    *,
    system_prompt: str,
    user_prompt: str,
    project: str,
    run_id: str | None = None,
    session_id: str | None = None,
    state_root: Path | None = None,
    budget: AttemptBudgetTracker | None = None,
    settings: Settings | None = None,
    max_tokens: int = 1024,
    timeout_seconds: float = 120.0,
    response_format: dict[str, Any] | str | None = None,
    temperature: float | None = None,
    complete_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Attempt completion across permitted routes under a shared attempt budget."""
    settings = settings or get_settings()
    tracker = budget or budget_from_env()
    complete = complete_fn or chat_completion
    candidates = _candidate_endpoints(role, project=project, settings=settings)
    attempts: list[RouteAttempt] = []
    req_hash = _request_hash(system_prompt, user_prompt)

    if not candidates:
        if state_root is not None:
            append_model_route_event(
                state_root,
                project=project,
                event_type=MODEL_ALL_ROUTES_FAILED,
                payload={
                    "run_id": run_id,
                    "session_id": session_id,
                    "role": role,
                    "reason": "no_candidates",
                    "request_hash": req_hash,
                    "budget": tracker.as_dict(),
                },
            )
        raise ModelRouteExhausted(f"no model routes for role={role} project={project}")

    for idx, (label, endpoint, leaves) in enumerate(candidates):
        kind = "provider_route" if idx > 0 else "infrastructure"
        if not tracker.consume(kind):
            break
        if state_root is not None:
            append_model_route_event(
                state_root,
                project=project,
                event_type=MODEL_ROUTE_ATTEMPTED,
                payload={
                    "run_id": run_id,
                    "session_id": session_id,
                    "role": role,
                    "model": endpoint.model,
                    "provider": endpoint.provider,
                    "endpoint_class": label,
                    "retry_number": tracker.total_completion_attempts,
                    "data_left_homelab": leaves,
                    "request_hash": req_hash,
                    "redacted_fields": ["system_prompt", "user_prompt"],
                },
            )
            if idx > 0:
                append_model_route_event(
                    state_root,
                    project=project,
                    event_type=MODEL_FALLBACK_SELECTED,
                    payload={
                        "run_id": run_id,
                        "session_id": session_id,
                        "role": role,
                        "model": endpoint.model,
                        "provider": endpoint.provider,
                        "endpoint_class": label,
                        "data_left_homelab": leaves,
                        "retry_number": tracker.total_completion_attempts,
                    },
                )

        import time

        started = time.perf_counter()
        try:
            result = complete(
                endpoint,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=max_tokens,
                timeout_seconds=timeout_seconds,
                response_format=response_format,
                temperature=temperature,
            )
            latency = (time.perf_counter() - started) * 1000.0
            usage = result.get("usage") or {}
            attempts.append(
                RouteAttempt(
                    provider=endpoint.provider,
                    model=endpoint.model,
                    base_url=endpoint.base_url,
                    endpoint_class=label,
                    data_left_homelab=leaves,
                    retry_number=tracker.total_completion_attempts,
                    ok=True,
                    latency_ms=latency,
                    token_counts=dict(usage) if isinstance(usage, dict) else {},
                )
            )
            if state_root is not None:
                append_model_route_event(
                    state_root,
                    project=project,
                    event_type=MODEL_CALL_COMPLETED,
                    payload={
                        "run_id": run_id,
                        "session_id": session_id,
                        "role": role,
                        "model": endpoint.model,
                        "provider": endpoint.provider,
                        "endpoint_class": label,
                        "latency_ms": latency,
                        "token_counts": usage,
                        "retry_number": tracker.total_completion_attempts,
                        "data_left_homelab": leaves,
                        "request_hash": req_hash,
                    },
                )
            return {
                **result,
                "route_attempts": [a.__dict__ for a in attempts],
                "budget": tracker.as_dict(),
                "fallback_used": idx > 0,
                "data_left_homelab": leaves,
            }
        except Exception as exc:
            latency = (time.perf_counter() - started) * 1000.0
            err = _error_class(exc)
            attempts.append(
                RouteAttempt(
                    provider=endpoint.provider,
                    model=endpoint.model,
                    base_url=endpoint.base_url,
                    endpoint_class=label,
                    data_left_homelab=leaves,
                    retry_number=tracker.total_completion_attempts,
                    ok=False,
                    error_class=err,
                    latency_ms=latency,
                )
            )
            if state_root is not None:
                append_model_route_event(
                    state_root,
                    project=project,
                    event_type=MODEL_ROUTE_FAILED,
                    payload={
                        "run_id": run_id,
                        "session_id": session_id,
                        "role": role,
                        "model": endpoint.model,
                        "provider": endpoint.provider,
                        "endpoint_class": label,
                        "error_class": err,
                        "latency_ms": latency,
                        "retry_number": tracker.total_completion_attempts,
                        "data_left_homelab": leaves,
                        "request_hash": req_hash,
                    },
                )
            logger.warning(
                "model_route_failed role=%s provider=%s error_class=%s",
                role,
                endpoint.provider,
                err,
            )
            continue

    if state_root is not None:
        append_model_route_event(
            state_root,
            project=project,
            event_type=MODEL_ALL_ROUTES_FAILED,
            payload={
                "run_id": run_id,
                "session_id": session_id,
                "role": role,
                "attempts": [a.__dict__ for a in attempts],
                "budget": tracker.as_dict(),
                "request_hash": req_hash,
            },
        )
    raise ModelRouteExhausted(
        f"all model routes failed for role={role}; attempts={len(attempts)} budget={tracker.as_dict()}"
    )


def context_controller_policy(
    *,
    recursion_needed: bool,
    controller_available: bool,
) -> str:
    """CT103-owned context policy (deterministic fallback outside LiteLLM)."""
    if not recursion_needed:
        return "deterministic_preflight"
    if controller_available:
        return "litellm_context_controller"
    return "deterministic_only"
