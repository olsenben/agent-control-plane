"""Single repair retry for structured output validation failures."""

from __future__ import annotations

import json
from typing import Any

from agent_control.model_router import ResolvedEndpoint
from agent_shared.models.context_pack import ContextPack
from agent_shared.models.plan import PlanResult
from agent_shared.models.review import ReviewResult
from agent_workers.rlm.completion import chat_completion


def _schema_for_kind(kind: str) -> dict[str, Any]:
    if kind == "plan":
        return PlanResult.model_json_schema()
    if kind == "review":
        return ReviewResult.model_json_schema()
    if kind == "fix":
        from agent_shared.models.fix import FixResult

        return FixResult.model_json_schema()
    raise ValueError(f"Unsupported repair kind: {kind!r}")


def build_repair_prompt(
    *,
    kind: str,
    bad_json: dict[str, Any],
    validation_errors: str,
    raw_excerpt: str,
    context_pack: ContextPack | None,
) -> tuple[str, str]:
    schema = _schema_for_kind(kind)
    platform_note = ""
    if context_pack is not None:
        platform_note = (
            "Platform-owned fields (blast_radius, prior_memory_used, context_sources) "
            "are supplied by the control plane and must not be invented. "
            "Omit or leave them unchanged if unsure.\n"
        )

    system_prompt = (
        "You correct malformed JSON model output. Return a single JSON object only "
        "(no markdown fences, no prose). Do not invent files, repos, run IDs, "
        "blast radius entries, or prior memory. Fix shape and type errors only."
    )
    user_prompt = (
        f"Command kind: {kind}\n"
        f"{platform_note}\n"
        f"Target JSON schema:\n{json.dumps(schema, indent=2)}\n\n"
        f"Validation errors:\n{validation_errors}\n\n"
        f"Malformed JSON:\n{json.dumps(bad_json, indent=2)[:4000]}\n\n"
        f"Raw model excerpt:\n{raw_excerpt[:2000]}\n\n"
        "Return corrected JSON only."
    )
    return system_prompt, user_prompt


def attempt_repair(
    *,
    kind: str,
    bad_json: dict[str, Any],
    validation_errors: str,
    raw_excerpt: str,
    context_pack: ContextPack | None,
    endpoint: ResolvedEndpoint,
    timeout_seconds: float = 60.0,
) -> str:
    system_prompt, user_prompt = build_repair_prompt(
        kind=kind,
        bad_json=bad_json,
        validation_errors=validation_errors,
        raw_excerpt=raw_excerpt,
        context_pack=context_pack,
    )
    result = chat_completion(
        endpoint,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_tokens=2048,
        timeout_seconds=timeout_seconds,
        response_format="json",
    )
    return str(result.get("content") or "").strip()


def attempt_json_only_retry(
    *,
    kind: str,
    raw_excerpt: str,
    endpoint: ResolvedEndpoint,
    timeout_seconds: float = 60.0,
) -> str:
    system_prompt = (
        "Return a single JSON object only. No markdown fences, no prose, no commentary."
    )
    user_prompt = (
        f"Command kind: {kind}\n"
        f"The previous response was not valid JSON:\n{raw_excerpt[:2000]}\n\n"
        "JSON object only, no markdown."
    )
    result = chat_completion(
        endpoint,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_tokens=2048,
        timeout_seconds=timeout_seconds,
        response_format="json",
        stream=False,
        temperature=0.0,
    )
    return str(result.get("content") or "").strip()


def attempt_missing_json_repair(
    *,
    kind: str,
    raw_excerpt: str,
    context_pack: ContextPack | None,
    endpoint: ResolvedEndpoint,
    timeout_seconds: float = 60.0,
) -> str:
    return attempt_repair(
        kind=kind,
        bad_json={},
        validation_errors="No JSON object found in model output",
        raw_excerpt=raw_excerpt,
        context_pack=context_pack,
        endpoint=endpoint,
        timeout_seconds=timeout_seconds,
    )
