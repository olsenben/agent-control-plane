"""Tests for review output parser."""

import json

import pytest

from agent_shared.models.review import ReviewResult
from agent_workers.rlm.json_extract import extract_json_blob
from agent_workers.rlm.review_parser import (
    ReviewParseError,
    filter_hallucinated_paths,
    parse_markdown_sections,
    parse_review_output,
)


def test_extract_json_blob_fenced() -> None:
    raw = 'Here is output:\n```json\n{"confidence": "high", "findings": []}\n```'
    data = extract_json_blob(raw)
    assert data["confidence"] == "high"


def test_parse_review_output_json() -> None:
    payload = {
        "findings": [
            {
                "id": "F-001",
                "severity": "info",
                "summary": "Looks good",
                "file": "README.md",
                "confidence": 0.9,
                "risk_tags": [],
            }
        ],
        "files_inspected": ["README.md"],
        "blast_radius": {"missing_graph_edges": ["not implemented"]},
        "confidence": "high",
        "recommended_next_command": "/agent plan",
        "risk_tags": [],
    }
    result = parse_review_output(json.dumps(payload))
    assert isinstance(result, ReviewResult)
    assert result.findings[0].id == "F-001"
    assert result.files_inspected == ["README.md"]


def test_parse_review_output_markdown_fallback() -> None:
    raw = """## Agent Review

### Finding
- [F-001] (warn) Missing error handling

### Files inspected
- src/main.py

### Cross-repo / blast-radius context
Potentially affected repos: (none)
Potentially affected services: (none)
Potentially affected tests: (none)
Related ADRs: (none)
missing_graph_edges: not implemented

### Confidence
medium

### Recommended next command
/agent plan
"""
    result = parse_review_output(raw)
    assert result.findings[0].severity == "warn"
    assert result.files_inspected == ["src/main.py"]
    assert result.recommended_next_command == "/agent plan"


def test_parse_review_output_invalid_raises() -> None:
    with pytest.raises(ReviewParseError):
        parse_review_output("not parseable at all")


def test_filter_hallucinated_paths() -> None:
    known = {"README.md", "src/app.py"}
    kept, rejected = filter_hallucinated_paths(
        ["README.md", "src/fake.py", "./src/app.py"],
        known,
    )
    assert "README.md" in kept
    assert "src/app.py" in kept
    assert "src/fake.py" in rejected


def test_filter_keeps_workspace_existing_file(tmp_path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "demo_app").mkdir()
    (tmp_path / "src" / "demo_app" / "math_service.py").write_text("x = 1\n", encoding="utf-8")
    kept, rejected = filter_hallucinated_paths(
        ["src/demo_app/math_service.py", "totally/missing.py"],
        {"gitea_issue", "graph_blast_radius"},
        workspace=tmp_path,
    )
    assert kept == ["src/demo_app/math_service.py"]
    assert "totally/missing.py" in rejected


def test_filter_plan_allows_new_file_under_existing_dir(tmp_path) -> None:
    (tmp_path / "tests").mkdir()
    kept, rejected = filter_hallucinated_paths(
        ["tests/test_new_helper.py", "nope/missing.py"],
        set(),
        workspace=tmp_path,
        allow_new_under_existing_dir=True,
    )
    assert kept == ["tests/test_new_helper.py"]
    assert "nope/missing.py" in rejected


def test_filter_rejects_pseudo_context_sources_as_files() -> None:
    kept, rejected = filter_hallucinated_paths(
        ["gitea_issue", "README.md"],
        {"gitea_issue", "README.md"},
    )
    assert kept == ["README.md"]
    assert "gitea_issue" in rejected


def test_parse_markdown_sections_risk_tags() -> None:
    raw = """### Finding
- [F-001] (info) ok

Risk tags: foo, bar

### Files inspected
- README.md

### Cross-repo / blast-radius context
missing_graph_edges: not implemented

### Confidence
high

### Recommended next command
/agent plan
"""
    data = parse_markdown_sections(raw)
    assert data["risk_tags"] == ["foo", "bar"]
