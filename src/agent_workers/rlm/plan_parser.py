"""Parse and validate structured plan model output."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from agent_shared.models.plan import PlanResult, PlanStep
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
        data = extract_json_blob(raw)
        return PlanResult.model_validate(data)
    except (ReviewParseError, json.JSONDecodeError, ValidationError) as exc:
        errors.append(str(exc))

    lowered = raw.lower()
    if "### steps" not in lowered and "### scope" not in lowered:
        raise PlanParseError(
            "Could not parse plan output as JSON or markdown sections: " + "; ".join(errors)
        )

    try:
        data = parse_markdown_sections(raw)
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
