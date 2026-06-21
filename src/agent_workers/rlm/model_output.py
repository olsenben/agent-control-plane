"""Structured output boundary: premerge, normalize, validate, optional repair."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import ValidationError

from agent_control.model_router import ResolvedEndpoint
from agent_shared.models.context_pack import ContextPack
from agent_shared.models.parse_failure import ParseFailureArtifact, RecommendedNextStep
from agent_shared.models.plan import PlanResult
from agent_shared.models.review import BlastRadiusContext, ReviewResult
from agent_workers.rlm.normalizers import normalize_plan_dict, normalize_review_dict
from agent_workers.rlm.premerge import premerge_platform_context
from agent_workers.rlm.repair import attempt_repair
from agent_workers.rlm.json_extract import JsonExtractError, extract_json_blob


class StructuredParseFailure(Exception):
    """Raised when model output cannot be validated after normalization and repair."""

    def __init__(self, artifact: ParseFailureArtifact):
        self.artifact = artifact
        super().__init__("; ".join(artifact.parse_errors) or "structured parse failed")


def _build_failure_artifact(
    *,
    kind: str,
    run_id: str,
    parse_errors: list[str],
    raw_response: str,
    context_pack: ContextPack | None,
) -> ParseFailureArtifact:
    blast = context_pack.blast_radius if context_pack is not None else BlastRadiusContext()
    prior: list[dict] = []
    if context_pack is not None and context_pack.prior_memory:
        from agent_workers.rlm.premerge import build_prior_memory_used_from_pack

        prior = build_prior_memory_used_from_pack(None, context_pack.prior_memory)
    return ParseFailureArtifact(
        run_id=run_id,
        command_kind=kind,
        parse_errors=parse_errors,
        raw_response_excerpt=raw_response[:2000],
        context_sources=list(context_pack.context_sources) if context_pack else [],
        blast_radius=blast,
        prior_memory_used=prior,
        recommended_next_step=RecommendedNextStep(),
    )


def _process_dict(
    kind: Literal["plan", "review"],
    data: dict[str, Any],
    *,
    context_pack: ContextPack | None,
) -> dict[str, Any]:
    merged = premerge_platform_context(kind, data, context_pack)
    if kind == "plan":
        return normalize_plan_dict(merged)
    return normalize_review_dict(merged)


def _validate_dict(
    kind: Literal["plan", "review"],
    data: dict[str, Any],
) -> PlanResult | ReviewResult:
    if kind == "plan":
        return PlanResult.model_validate(data)
    return ReviewResult.model_validate(data)


def validate_or_repair(
    kind: Literal["plan", "review"],
    raw: str,
    *,
    context_pack: ContextPack | None = None,
    run_id: str = "",
    repair_endpoint: ResolvedEndpoint | None = None,
    repair_timeout_seconds: float = 60.0,
    markdown_fallback: dict[str, Any] | None = None,
) -> PlanResult | ReviewResult:
    """Extract, premerge, normalize, validate; one repair retry on ValidationError."""
    if not raw or not raw.strip():
        raise StructuredParseFailure(
            _build_failure_artifact(
                kind=kind,
                run_id=run_id,
                parse_errors=[f"Empty {kind} model output"],
                raw_response=raw or "",
                context_pack=context_pack,
            )
        )

    errors: list[str] = []
    candidate_dict: dict[str, Any] | None = None

    try:
        candidate_dict = extract_json_blob(raw)
    except (JsonExtractError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
        if markdown_fallback is not None:
            candidate_dict = markdown_fallback

    if candidate_dict is None:
        raise StructuredParseFailure(
            _build_failure_artifact(
                kind=kind,
                run_id=run_id,
                parse_errors=errors or ["No JSON object found in model output"],
                raw_response=raw,
                context_pack=context_pack,
            )
        )

    processed = _process_dict(kind, candidate_dict, context_pack=context_pack)
    validation_error: ValidationError | None = None
    try:
        return _validate_dict(kind, processed)
    except ValidationError as exc:
        validation_error = exc
        errors.append(str(exc))

    if repair_endpoint is not None and validation_error is not None:
        try:
            repaired_raw = attempt_repair(
                kind=kind,
                bad_json=processed,
                validation_errors=str(validation_error),
                raw_excerpt=raw,
                context_pack=context_pack,
                endpoint=repair_endpoint,
                timeout_seconds=repair_timeout_seconds,
            )
            repaired_dict = extract_json_blob(repaired_raw)
            processed = _process_dict(kind, repaired_dict, context_pack=context_pack)
            return _validate_dict(kind, processed)
        except (JsonExtractError, json.JSONDecodeError, ValidationError) as repair_exc:
            errors.append(f"repair failed: {repair_exc}")

    raise StructuredParseFailure(
        _build_failure_artifact(
            kind=kind,
            run_id=run_id,
            parse_errors=errors,
            raw_response=raw,
            context_pack=context_pack,
        )
    )
