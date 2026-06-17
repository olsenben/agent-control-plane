"""Parse and validate structured review model output."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from agent_shared.models.review import (
    BlastRadiusContext,
    ReviewFinding,
    ReviewResult,
    stub_blast_radius,
)


class ReviewParseError(ValueError):
    """Raised when review output cannot be parsed into ReviewResult."""


def _normalize_path(path: str) -> str:
    cleaned = path.strip().replace("\\", "/")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned.lstrip("/")


def filter_hallucinated_paths(
    files: list[str],
    known_sources: set[str],
) -> tuple[list[str], list[str]]:
    normalized_known = {_normalize_path(p) for p in known_sources}
    kept: list[str] = []
    rejected: list[str] = []
    for raw in files:
        norm = _normalize_path(raw)
        if not norm:
            continue
        if norm in normalized_known:
            kept.append(norm)
            continue
        if any(norm.endswith(f"/{known}") or known.endswith(f"/{norm}") for known in normalized_known):
            kept.append(norm)
            continue
        rejected.append(raw)
    return kept, rejected


def extract_json_blob(raw: str) -> dict[str, Any]:
    text = raw.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if fence_match:
        return json.loads(fence_match.group(1))
    start = text.find("{")
    if start < 0:
        raise ReviewParseError("No JSON object found in model output")
    depth = 0
    for idx in range(start, len(text)):
        ch = text[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : idx + 1])
    raise ReviewParseError("Unbalanced JSON object in model output")


def _section_text(raw: str, heading: str) -> str:
    pattern = rf"###\s*{re.escape(heading)}\s*\n(.*?)(?=\n###\s|\Z)"
    match = re.search(pattern, raw, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _parse_list_section(text: str) -> list[str]:
    items: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.lower() in {"(none)", "none"}:
            continue
        if stripped.startswith("- "):
            items.append(stripped[2:].strip())
        elif stripped.startswith("* "):
            items.append(stripped[2:].strip())
        elif ":" not in stripped:
            items.append(stripped)
    return items


def _parse_blast_radius(text: str) -> BlastRadiusContext:
    br = BlastRadiusContext()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        key = key.lower().strip()
        value = value.strip()
        if value.lower() in {"(none)", "none"}:
            value_list: list[str] = []
        elif key == "missing_graph_edges":
            value_list = [v.strip() for v in value.split(",") if v.strip()]
        else:
            value_list = [v.strip() for v in value.split(",") if v.strip()]
        if key.startswith("potentially affected repos"):
            br.affected_repos = value_list
        elif key.startswith("potentially affected services"):
            br.affected_services = value_list
        elif key.startswith("potentially affected tests"):
            br.affected_tests = value_list
        elif key.startswith("related adrs"):
            br.related_adrs = value_list
        elif key == "missing_graph_edges":
            br.missing_graph_edges = value_list
    return br


def parse_markdown_sections(raw: str) -> dict[str, Any]:
    finding_text = _section_text(raw, "Finding")
    files_text = _section_text(raw, "Files inspected")
    blast_text = _section_text(raw, "Cross-repo / blast-radius context")
    confidence = _section_text(raw, "Confidence") or "medium"
    next_cmd = _section_text(raw, "Recommended next command") or "/agent plan"

    findings: list[dict[str, Any]] = []
    for line in finding_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.lower() == "(none)":
            continue
        if stripped.startswith("- "):
            stripped = stripped[2:].strip()
        match = re.match(
            r"\[(?P<id>[^\]]+)\]\s*\((?P<severity>info|warn|error)\)(?:\s*\((?P<file>[^)]+)\))?\s*(?P<summary>.+)",
            stripped,
            re.IGNORECASE,
        )
        if match:
            findings.append(
                {
                    "id": match.group("id"),
                    "severity": match.group("severity").lower(),
                    "file": match.group("file"),
                    "summary": match.group("summary").strip(),
                    "confidence": 0.5,
                    "risk_tags": [],
                }
            )
        else:
            findings.append(
                {
                    "id": f"F-{len(findings) + 1:03d}",
                    "severity": "info",
                    "summary": stripped,
                    "confidence": 0.5,
                    "risk_tags": [],
                }
            )

    risk_tags: list[str] = []
    for line in raw.splitlines():
        if line.lower().startswith("risk tags:"):
            risk_tags = [t.strip() for t in line.split(":", 1)[1].split(",") if t.strip()]

    return {
        "findings": findings,
        "files_inspected": _parse_list_section(files_text),
        "blast_radius": _parse_blast_radius(blast_text).model_dump(mode="json"),
        "confidence": confidence.splitlines()[0].strip() if confidence else "medium",
        "recommended_next_command": next_cmd.splitlines()[0].strip() if next_cmd else "/agent plan",
        "risk_tags": risk_tags,
    }


def parse_review_output(raw: str) -> ReviewResult:
    if not raw or not raw.strip():
        raise ReviewParseError("Empty review model output")

    errors: list[str] = []
    try:
        data = extract_json_blob(raw)
        return ReviewResult.model_validate(data)
    except (ReviewParseError, json.JSONDecodeError, ValidationError) as exc:
        errors.append(str(exc))

    lowered = raw.lower()
    if "### finding" not in lowered and "### files inspected" not in lowered:
        raise ReviewParseError(
            "Could not parse review output as JSON or markdown sections: " + "; ".join(errors)
        )

    try:
        data = parse_markdown_sections(raw)
        return ReviewResult.model_validate(data)
    except ValidationError as exc:
        errors.append(str(exc))

    raise ReviewParseError(
        "Could not parse review output as JSON or markdown sections: " + "; ".join(errors)
    )


def apply_path_validation(
    review: ReviewResult,
    known_sources: set[str],
) -> tuple[ReviewResult, list[str]]:
    warnings: list[str] = []
    kept_files, rejected_files = filter_hallucinated_paths(review.files_inspected, known_sources)
    if rejected_files:
        warnings.append(f"Rejected hallucinated file paths: {', '.join(rejected_files)}")

    validated_findings: list[ReviewFinding] = []
    for finding in review.findings:
        if finding.file:
            kept, rejected = filter_hallucinated_paths([finding.file], known_sources)
            if rejected:
                warnings.append(f"Cleared hallucinated finding file: {finding.file}")
                validated_findings.append(finding.model_copy(update={"file": None}))
            else:
                validated_findings.append(finding.model_copy(update={"file": kept[0] if kept else None}))
        else:
            validated_findings.append(finding)

    blast = review.blast_radius
    if not any(
        [
            blast.affected_repos,
            blast.affected_services,
            blast.affected_tests,
            blast.related_adrs,
            blast.missing_graph_edges,
        ]
    ):
        blast = stub_blast_radius()

    updated = review.model_copy(
        update={
            "files_inspected": kept_files,
            "findings": validated_findings,
            "blast_radius": blast,
        }
    )
    return updated, warnings
