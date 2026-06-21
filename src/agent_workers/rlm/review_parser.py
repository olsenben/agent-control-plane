"""Parse and validate structured review model output."""

from __future__ import annotations

import re
from typing import Any

from agent_control.model_router import ResolvedEndpoint
from agent_shared.models.context_pack import ContextPack
from agent_shared.models.review import (
    BlastRadiusContext,
    ReviewFinding,
    ReviewResult,
    stub_blast_radius,
)
from agent_workers.rlm.model_output import StructuredParseFailure, validate_or_repair
from agent_workers.rlm.normalizers import parse_blast_radius_lines


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
    return parse_blast_radius_lines(text)


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


def parse_review_output(
    raw: str,
    *,
    context_pack: ContextPack | None = None,
    run_id: str = "",
    repair_endpoint: ResolvedEndpoint | None = None,
    repair_timeout_seconds: float = 60.0,
) -> ReviewResult:
    markdown_data: dict[str, Any] | None = None
    lowered = raw.lower() if raw else ""
    if "### finding" in lowered or "### files inspected" in lowered:
        markdown_data = parse_markdown_sections(raw)

    try:
        result = validate_or_repair(
            "review",
            raw,
            context_pack=context_pack,
            run_id=run_id,
            repair_endpoint=repair_endpoint,
            repair_timeout_seconds=repair_timeout_seconds,
            markdown_fallback=markdown_data,
        )
    except StructuredParseFailure as exc:
        raise ReviewParseError(
            "Could not parse review output as JSON or markdown sections: "
            + "; ".join(exc.artifact.parse_errors)
        ) from exc

    if not isinstance(result, ReviewResult):
        raise ReviewParseError("Internal error: expected ReviewResult")
    return result


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
