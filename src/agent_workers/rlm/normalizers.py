"""Shared normalizers for plan/review model output dicts."""

from __future__ import annotations


from typing import Any

from agent_shared.models.review import BlastRadiusContext, stub_blast_radius


def parse_blast_radius_lines(text: str) -> BlastRadiusContext:
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


def _blast_radius_has_data(br: BlastRadiusContext) -> bool:
    return bool(
        br.affected_repos
        or br.affected_services
        or br.affected_tests
        or br.related_adrs
        or br.missing_graph_edges
    )


def coerce_string_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [line.strip() for line in raw.splitlines() if line.strip()]
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []


def coerce_prior_memory_used(raw: Any) -> list[dict[str, Any]]:
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


def coerce_blast_radius(raw: Any) -> dict[str, Any]:
    """Coerce model output where blast_radius is prose instead of structured fields."""
    if isinstance(raw, dict):
        return raw
    if raw is None:
        return stub_blast_radius().model_dump(mode="json")
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return stub_blast_radius().model_dump(mode="json")
        parsed = parse_blast_radius_lines(text)
        if _blast_radius_has_data(parsed):
            return parsed.model_dump(mode="json")
        return BlastRadiusContext(
            missing_graph_edges=[f"model_narrative: {text[:500]}"]
        ).model_dump(mode="json")
    return stub_blast_radius().model_dump(mode="json")


def coerce_findings(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    findings: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if isinstance(item, str):
            summary = item.strip()
            if not summary:
                continue
            findings.append(
                {
                    "id": f"F-{index + 1:03d}",
                    "severity": "info",
                    "summary": summary,
                    "confidence": 0.5,
                    "risk_tags": [],
                }
            )
            continue
        if isinstance(item, dict):
            findings.append(dict(item))
    return findings


def coerce_files_inspected(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        stripped = raw.strip()
        return [stripped] if stripped else []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []


def coerce_plan_steps(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    steps: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if isinstance(item, str):
            summary = item.strip()
            if not summary:
                continue
            steps.append({"id": f"S-{index + 1:03d}", "summary": summary, "files": []})
            continue
        if isinstance(item, dict):
            steps.append(dict(item))
    return steps


def coerce_confidence(raw: Any) -> str:
    if raw is None:
        return "medium"
    if isinstance(raw, (int, float)):
        if raw >= 0.75:
            return "high"
        if raw >= 0.4:
            return "medium"
        return "low"
    text = str(raw).strip().lower()
    if text in {"low", "medium", "high"}:
        return text
    return "medium"


def normalize_plan_dict(data: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(data)
    if "prior_memory_used" in normalized:
        normalized["prior_memory_used"] = coerce_prior_memory_used(normalized.get("prior_memory_used"))
    if "blast_radius" in normalized:
        normalized["blast_radius"] = coerce_blast_radius(normalized.get("blast_radius"))
    if "steps" in normalized:
        normalized["steps"] = coerce_plan_steps(normalized.get("steps"))
    for list_field in ("ci_hints", "assumptions", "open_questions", "risk_tags"):
        if list_field in normalized and not isinstance(normalized[list_field], list):
            normalized[list_field] = coerce_string_list(normalized.get(list_field))
    if "confidence" in normalized:
        normalized["confidence"] = coerce_confidence(normalized.get("confidence"))
    return normalized


def normalize_review_dict(data: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(data)
    if "findings" in normalized:
        normalized["findings"] = coerce_findings(normalized.get("findings"))
    if "files_inspected" in normalized:
        normalized["files_inspected"] = coerce_files_inspected(normalized.get("files_inspected"))
    if "blast_radius" in normalized:
        normalized["blast_radius"] = coerce_blast_radius(normalized.get("blast_radius"))
    if "risk_tags" in normalized and not isinstance(normalized["risk_tags"], list):
        normalized["risk_tags"] = coerce_string_list(normalized.get("risk_tags"))
    if "confidence" in normalized:
        normalized["confidence"] = coerce_confidence(normalized.get("confidence"))
    return normalized
