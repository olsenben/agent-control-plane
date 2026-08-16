"""Live 2070 controller client for the recursive context worker (V10 T00.5).

The C1 arm routes `call_primary_model` through the CT103 model gateway to the
role that maps to `MODEL_2070_*`. The controller stays read-only: it receives
the focused question plus evidence *references* only, never repository content,
secrets, or policy authority. Any model failure degrades to the deterministic
summary so the worker still returns a valid `recursive_context_result.v1`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
    gpu_seconds: float = 0.0
    data_left_homelab: bool = False
    error_class: str = ""
    planned_model_id: str = ""
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "controller_backend": self.backend,
            "controller_role": self.role,
            "controller_role_label": self.role_label,
            "controller_model_invoked": self.model_invoked,
            "controller_model_id": self.model_id,
            "controller_provider": self.provider,
            "controller_attempts": self.attempts,
            "controller_prompt_tokens": self.prompt_tokens,
            "controller_completion_tokens": self.completion_tokens,
            "controller_wall_seconds": round(self.wall_seconds, 3),
            "controller_gpu_seconds": round(self.gpu_seconds, 3),
            "controller_data_left_homelab": self.data_left_homelab,
            "controller_error_class": self.error_class,
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


def _gpu_seconds(usage: dict[str, Any]) -> float:
    """Ollama-style nanosecond eval timings when the endpoint reports them."""
    for key, scale in (("eval_duration", 1e-9), ("gpu_seconds", 1.0), ("gpu_ms", 1e-3)):
        value = usage.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return float(value) * scale
    return 0.0


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
            )
        except Exception as exc:  # noqa: BLE001 — fail soft into C0 behaviour
            telemetry.wall_seconds += time.perf_counter() - started
            telemetry.error_class = type(exc).__name__
            telemetry.errors.append(str(exc)[:200])
            if not telemetry.model_id:
                telemetry.model_id = telemetry.planned_model_id
            return _deterministic_result(question, evidence, "controller_unavailable")

        telemetry.wall_seconds += time.perf_counter() - started
        usage = response.get("usage") or {}
        usage = usage if isinstance(usage, dict) else {}
        telemetry.model_invoked = True
        telemetry.model_id = str(response.get("model") or telemetry.planned_model_id or "")
        telemetry.provider = str(response.get("provider") or "")
        telemetry.prompt_tokens += int(usage.get("prompt_tokens") or 0)
        telemetry.completion_tokens += int(usage.get("completion_tokens") or 0)
        telemetry.gpu_seconds += _gpu_seconds(usage)
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
