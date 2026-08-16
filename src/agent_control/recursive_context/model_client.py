"""Live 2070 controller client for the recursive context worker (V10 T00.5).

The C1 arm routes `call_primary_model` through the CT103 model gateway to the
role that maps to `MODEL_2070_*`. The controller stays read-only: it receives
the focused question plus evidence *references* only, never repository content,
secrets, or policy authority. Any model failure degrades to the deterministic
summary so the worker still returns a valid `recursive_context_result.v1`.

V10 Wave C hardening: the controller is local-only by construction. Every route
the failover chain offers is checked before a request is sent, and any route
that is not a homelab GPU endpoint is refused rather than attempted, so a C1
observation can never be answered by an external provider. Endpoint-reported
timings that are absent stay `None` and are named in `missing_fields` instead of
being recorded as a measured `0.0`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from ipaddress import ip_address, ip_network
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from agent_control.config import Settings
from agent_control.model_gateway import chat_completion_with_failover
from agent_control.recursive_context.tools import PrimaryModelFn, ToolResult
from agent_shared.models.recursive_context import RecursiveContextBudget

CONTROLLER_SYSTEM_PROMPT = (
    "You are a read-only context controller for a software maintenance agent. "
    "You may only reason over the evidence references you are given and ask for "
    "more evidence. You have no authority over policy, budgets, credentials, "
    "verification, publication, or repository state. Cite the evidence "
    "references you relied on. Answer in at most 8 lines of plain text."
)


LOCAL_PROVIDERS: frozenset[str] = frozenset({"gpu"})
HOMELAB_HOST_SUFFIXES: tuple[str, ...] = (".ts.net", ".local", ".lan", ".internal")
TAILSCALE_CGNAT = ip_network("100.64.0.0/10")


class ControllerEgressRefused(RuntimeError):
    """A non-homelab route was offered to the read-only C1 controller."""


def endpoint_is_homelab(base_url: str) -> bool:
    """True when the URL names a loopback, RFC1918, or tailnet host."""
    host = (urlsplit(base_url).hostname or "").strip().lower()
    if not host:
        return False
    try:
        addr = ip_address(host)
    except ValueError:
        if "." not in host:
            # Bare hostname: a compose service or tailnet MagicDNS short name.
            return True
        return host.endswith(HOMELAB_HOST_SUFFIXES)
    return bool(addr.is_loopback or addr.is_private or addr.is_link_local) or addr in (
        TAILSCALE_CGNAT
    )


@dataclass
class ControllerTelemetry:
    """Proof of whether the configured 2070 controller actually ran."""

    backend: str = "deterministic"
    role: str = ""
    role_label: str = ""
    model_invoked: bool = False
    model_id: str = ""
    provider: str = ""
    attempts: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    wall_seconds: float = 0.0
    gpu_seconds: float | None = None
    data_left_homelab: bool = False
    error_class: str = ""
    planned_model_id: str = ""
    model_id_source: str = ""
    errors: list[str] = field(default_factory=list)
    local_only_enforced: bool = False
    external_routes_refused: int = 0
    route_class: str = ""
    endpoint_base_url: str = ""
    missing_fields: list[str] = field(default_factory=list)

    def note_missing(self, name: str) -> None:
        if name not in self.missing_fields:
            self.missing_fields.append(name)

    def as_dict(self) -> dict[str, Any]:
        return {
            "controller_backend": self.backend,
            "controller_role": self.role,
            "controller_role_label": self.role_label,
            "controller_model_invoked": self.model_invoked,
            "controller_model_id": self.model_id,
            "controller_model_id_source": self.model_id_source,
            "controller_provider": self.provider,
            "controller_attempts": self.attempts,
            "controller_prompt_tokens": self.prompt_tokens,
            "controller_completion_tokens": self.completion_tokens,
            "controller_wall_seconds": round(self.wall_seconds, 3),
            "controller_gpu_seconds": (
                None if self.gpu_seconds is None else round(self.gpu_seconds, 3)
            ),
            "controller_data_left_homelab": self.data_left_homelab,
            "controller_error_class": self.error_class,
            "controller_local_only_enforced": self.local_only_enforced,
            "controller_external_routes_refused": self.external_routes_refused,
            "controller_route_class": self.route_class,
            "controller_endpoint_base_url": self.endpoint_base_url,
            "controller_missing_fields": sorted(self.missing_fields),
        }


def resolve_controller_model_id(role: str, settings: Settings) -> str:
    """Best-effort pre-call model id, used when every route fails."""
    try:
        from agent_control.model_gateway import gateway_endpoint_for_role
        from agent_control.model_router import resolve_role_primary

        gateway = gateway_endpoint_for_role(role, settings)
        endpoint = gateway or resolve_role_primary(role, settings)
        return endpoint.model or ""
    except Exception:  # noqa: BLE001 — telemetry only, never blocks the run
        return ""


def _gpu_seconds(usage: dict[str, Any]) -> float | None:
    """Ollama-style nanosecond eval timings, or None when unreported.

    An endpoint that does not expose timings is not a zero-cost endpoint, so the
    absent value stays `None` and the caller names it in `missing_fields`.
    """
    for key, scale in (("eval_duration", 1e-9), ("gpu_seconds", 1.0), ("gpu_ms", 1e-3)):
        value = usage.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
            return float(value) * scale
    return None


def _local_only_complete(telemetry: ControllerTelemetry) -> Any:
    """Wrap `chat_completion` so only homelab GPU endpoints are ever contacted."""

    def _complete(endpoint: Any, **kwargs: Any) -> dict[str, Any]:
        provider = str(getattr(endpoint, "provider", "") or "")
        base_url = str(getattr(endpoint, "base_url", "") or "")
        if provider not in LOCAL_PROVIDERS or not endpoint_is_homelab(base_url):
            telemetry.external_routes_refused += 1
            raise ControllerEgressRefused(
                f"C1 controller refused non-homelab route provider={provider or 'unset'}"
            )
        telemetry.endpoint_base_url = base_url
        from agent_workers.rlm.completion import chat_completion

        return chat_completion(endpoint, **kwargs)

    return _complete


def _route_class(role: str, settings: Settings) -> str:
    """`direct_local` when ACP dials the GPU itself, `gateway_indirect` via proxy."""
    try:
        from agent_control.model_gateway import gateway_endpoint_for_role

        return "gateway_indirect" if gateway_endpoint_for_role(role, settings) else "direct_local"
    except Exception:  # noqa: BLE001 — telemetry only, never blocks the run
        return "unknown"


def _deterministic_result(question: str, evidence: list[str], reason: str) -> ToolResult:
    return ToolResult(
        tool="call_primary_model",
        ok=True,
        summary=f"fallback_deterministic ({reason}): {question[:120]}",
        evidence_refs=evidence,
        data={"mode": "fallback_deterministic", "question": question, "reason": reason},
    )


def build_controller_model_fn(
    *,
    role: str,
    role_label: str,
    project: str,
    run_id: str,
    session_id: str,
    budget: RecursiveContextBudget,
    settings: Settings,
    state_root: Path | None = None,
    telemetry: ControllerTelemetry,
) -> PrimaryModelFn:
    """Return a `call_primary_model` implementation backed by the 2070 role."""
    telemetry.backend = "model"
    telemetry.role = role
    telemetry.role_label = role_label
    telemetry.planned_model_id = resolve_controller_model_id(role, settings)
    telemetry.local_only_enforced = True
    telemetry.route_class = _route_class(role, settings)
    if telemetry.route_class == "gateway_indirect":
        # A proxy in front of the GPUs can egress without ACP seeing it, so the
        # trust boundary is not provable from this side.
        telemetry.note_missing("controller_data_left_homelab")
    complete_fn = _local_only_complete(telemetry)

    def _call(question: str, evidence_refs: list[str]) -> ToolResult:
        evidence = list(evidence_refs)
        if telemetry.prompt_tokens >= budget.max_total_input_tokens:
            telemetry.error_class = "budget_exhausted"
            return _deterministic_result(question, evidence, "input_token_budget")

        prompt = "\n".join(
            [
                f"Question: {question}",
                "",
                "Evidence references (identifiers only, no file contents):",
                *(f"- {ref}" for ref in evidence[:50]),
                "",
                "State which references support or contradict the question, and name "
                "the single most useful next piece of evidence.",
            ]
        )[: budget.output_max_chars]

        telemetry.attempts += 1
        started = time.perf_counter()
        try:
            response = chat_completion_with_failover(
                role,
                system_prompt=CONTROLLER_SYSTEM_PROMPT,
                user_prompt=prompt,
                project=project,
                run_id=run_id or None,
                session_id=session_id or None,
                state_root=state_root,
                settings=settings,
                max_tokens=min(1024, budget.max_total_output_tokens),
                timeout_seconds=float(budget.max_wall_seconds),
                complete_fn=complete_fn,
            )
        except Exception as exc:  # noqa: BLE001 — fail soft into C0 behaviour
            telemetry.wall_seconds += time.perf_counter() - started
            telemetry.error_class = (
                "external_route_refused"
                if telemetry.external_routes_refused
                else type(exc).__name__
            )
            telemetry.errors.append(str(exc)[:200])
            if not telemetry.model_id:
                telemetry.model_id = telemetry.planned_model_id
                telemetry.model_id_source = "planned_not_invoked"
            for name in ("controller_prompt_tokens", "controller_completion_tokens"):
                telemetry.note_missing(name)
            telemetry.note_missing("controller_gpu_seconds")
            return _deterministic_result(question, evidence, "controller_unavailable")

        telemetry.wall_seconds += time.perf_counter() - started
        usage = response.get("usage") or {}
        usage = usage if isinstance(usage, dict) else {}
        telemetry.model_invoked = True
        reported = str(response.get("model_reported") or "").strip()
        if reported:
            telemetry.model_id = reported
            telemetry.model_id_source = "endpoint_reported"
        else:
            telemetry.model_id = str(response.get("model") or telemetry.planned_model_id or "")
            telemetry.model_id_source = "configured"
            telemetry.note_missing("controller_model_id")
        telemetry.provider = str(response.get("provider") or "")
        for field_name, usage_key in (
            ("controller_prompt_tokens", "prompt_tokens"),
            ("controller_completion_tokens", "completion_tokens"),
        ):
            if usage.get(usage_key) is None:
                telemetry.note_missing(field_name)
        telemetry.prompt_tokens += int(usage.get("prompt_tokens") or 0)
        telemetry.completion_tokens += int(usage.get("completion_tokens") or 0)
        gpu_seconds = _gpu_seconds(usage)
        if gpu_seconds is None:
            telemetry.note_missing("controller_gpu_seconds")
        else:
            telemetry.gpu_seconds = (telemetry.gpu_seconds or 0.0) + gpu_seconds
        telemetry.data_left_homelab = telemetry.data_left_homelab or bool(
            response.get("data_left_homelab")
        )
        content = str(response.get("content") or "").strip()
        if not content:
            telemetry.error_class = "empty_completion"
            return _deterministic_result(question, evidence, "empty_completion")
        return ToolResult(
            tool="call_primary_model",
            ok=True,
            summary=content[: budget.output_max_chars],
            evidence_refs=evidence,
            data={
                "mode": "model_2070",
                "question": question,
                "model": telemetry.model_id,
                "provider": telemetry.provider,
            },
        )

    return _call
