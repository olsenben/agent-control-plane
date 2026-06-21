"""Parse and validate structured plan model output."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from agent_shared.models.plan import PlanResult, PlanStep
from agent_shared.models.review import BlastRadiusContext, stub_blast_radius
from agent_workers.rlm.review_parser import (
    ReviewParseError,
    _parse_blast_radius,
    _parse_list_section,
    _section_text,
    extract_json_blob,
    filter_hallucinated_paths,
)


class PlanParseError(ValueError):
    """Raised when plan output cannot be parsed into PlanResult."""


def _normalize_prior_memory_used(raw: Any) -> list[dict[str, Any]]:
    """Coerce model output where prior_memory_used is a list of run_id strings."""
    if not isinstance(raw, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, str):
            run_id = item.strip()
            if run_id:
                normalized.append({"run_id": run_id, "used_for": "plan_context"})
            continue
        if isinstance(item, dict):
            entry = dict(item)
            run_id = str(entry.get("run_id") or entry.get("source_run_id") or "").strip()
            if not run_id:
                continue
            entry["run_id"] = run_id
            entry.setdefault("used_for", "plan_context")
            normalized.append(entry)
    return normalized


def _blast_radius_has_data(br: BlastRadiusContext) -> bool:
    return any(
        [
            br.affected_repos,
            br.affected_services,
            br.affected_tests,
            br.related_adrs,
            br.missing_graph_edges,
        ]
    )


def _normalize_blast_radius(raw: Any) -> dict[str, Any]:
    """Coerce model output where blast_radius is prose instead of structured fields."""
    if raw is None:
        return stub_blast_radius().model_dump(mode="json")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return stub_blast_radius().model_dump(mode="json")
        parsed = _parse_blast_radius(text)
        if _blast_radius_has_data(parsed):
            return parsed.model_dump(mode="json")
        return BlastRadiusContext(
            missing_graph_edges=[f"model_narrative: {text[:500]}"]
        ).model_dump(mode="json")
    return stub_blast_radius().model_dump(mode="json")


def _normalize_string_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [line.strip() for line in raw.splitlines() if line.strip()]
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []


def _normalize_plan_data(data: dict[str, Any]) -> dict[str, Any]:
    data = dict(data)
    if "prior_memory_used" in data:
        data["prior_memory_used"] = _normalize_prior_memory_used(data.get("prior_memory_used"))
    if "blast_radius" in data:
        data["blast_radius"] = _normalize_blast_radius(data.get("blast_radius"))
    for list_field in ("ci_hints", "assumptions", "open_questions", "risk_tags"):
        if list_field in data and not isinstance(data[list_field], list):
            data[list_field] = _normalize_string_list(data.get(list_field))
    return data


def parse_markdown_sections(raw: str) -> dict[str, Any]:
    scope = _section_text(raw, "Scope") or ""
    steps_text = _section_text(raw, "Steps")
    ci_text = _section_text(raw, "CI hints")
    blast_text = _section_text(raw, "Cross-repo / blast-radius context")
    assumptions_text = _section_text(raw, "Assumptions")
    questions_text = _section_text(raw, "Open questions")
    confidence = _section_text(raw, "Confidence") or "medium"
    next_cmd = _section_text(raw, "Recommended next command") or "/agent fix"

    steps: list[dict[str, Any]] = []
    for line in steps_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.lower() == "(none)":
            continue
        if stripped.startswith("- "):
            stripped = stripped[2:].strip()
        match = re.match(
            r"\[(?P<id>[^\]]+)\](?:\s*\((?P<files>[^)]+)\))?\s*(?P<summary>.+)",
            stripped,
        )
        if match:
            files_raw = match.group("files") or ""
            files = [f.strip() for f in files_raw.split(",") if f.strip()] if files_raw else []
            steps.append(
                {
                    "id": match.group("id"),
                    "summary": match.group("summary").strip(),
                    "files": files,
                }
            )
        else:
            steps.append({"id": f"S-{len(steps) + 1:03d}", "summary": stripped, "files": []})

    risk_tags: list[str] = []
    for line in raw.splitlines():
        if line.lower().startswith("risk tags:"):
            risk_tags = [t.strip() for t in line.split(":", 1)[1].split(",") if t.strip()]

    return {
        "scope_summary": scope.splitlines()[0].strip() if scope else "",
        "steps": steps,
        "ci_hints": _parse_list_section(ci_text),
        "blast_radius": _parse_blast_radius(blast_text).model_dump(mode="json"),
        "assumptions": _parse_list_section(assumptions_text),
        "open_questions": _parse_list_section(questions_text),
        "confidence": confidence.splitlines()[0].strip() if confidence else "medium",
        "recommended_next_command": next_cmd.splitlines()[0].strip() if next_cmd else "/agent fix",
        "risk_tags": risk_tags,
    }


def parse_plan_output(raw: str) -> PlanResult:
    if not raw or not raw.strip():
        raise PlanParseError("Empty plan model output")

    errors: list[str] = []
    try:
        data = _normalize_plan_data(extract_json_blob(raw))
        return PlanResult.model_validate(data)
    except (ReviewParseError, json.JSONDecodeError, ValidationError) as exc:
        errors.append(str(exc))

    lowered = raw.lower()
    if "### steps" not in lowered and "### scope" not in lowered:
        raise PlanParseError(
            "Could not parse plan output as JSON or markdown sections: " + "; ".join(errors)
        )

    try:
        data = _normalize_plan_data(parse_markdown_sections(raw))
        return PlanResult.model_validate(data)
    except ValidationError as exc:
        errors.append(str(exc))

    raise PlanParseError(
        "Could not parse plan output as JSON or markdown sections: " + "; ".join(errors)
    )


def apply_path_validation(
    plan: PlanResult,
    known_sources: set[str],
) -> tuple[PlanResult, list[str]]:
    warnings: list[str] = []
    validated_steps: list[PlanStep] = []
    for step in plan.steps:
        if not step.files:
            validated_steps.append(step)
            continue
        kept, rejected = filter_hallucinated_paths(step.files, known_sources)
        if rejected:
            warnings.append(f"Rejected hallucinated step file paths: {', '.join(rejected)}")
        validated_steps.append(step.model_copy(update={"files": kept}))

    blast = plan.blast_radius
    if not any(
        [
            blast.affected_repos,
            blast.affected_services,
            blast.affected_tests,
            blast.related_adrs,
            blast.missing_graph_edges,
        ]
    ):
        from agent_shared.models.review import stub_blast_radius

        blast = stub_blast_radius()

    updated = plan.model_copy(update={"steps": validated_steps, "blast_radius": blast})
    return updated, warnings
