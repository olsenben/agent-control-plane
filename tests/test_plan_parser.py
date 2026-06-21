"""Tests for plan output parser."""

import json

import pytest

from agent_shared.models.plan import PlanResult
from agent_workers.rlm.plan_parser import PlanParseError, parse_plan_output


def test_parse_plan_output_json() -> None:
    payload = {
        "scope_summary": "Add graph-aware planning",
        "steps": [{"id": "S-001", "summary": "Wire plan engine", "files": ["README.md"]}],
        "ci_hints": ["pytest tests/test_plan_parser.py"],
        "blast_radius": {"missing_graph_edges": ["not implemented"]},
        "assumptions": ["Read-only plan"],
        "open_questions": [],
        "confidence": "high",
        "recommended_next_command": "/agent fix",
        "risk_tags": [],
    }
    result = parse_plan_output(json.dumps(payload))
    assert isinstance(result, PlanResult)
    assert result.steps[0].id == "S-001"
    assert result.ci_hints[0].startswith("pytest")


def test_parse_plan_output_markdown_fallback() -> None:
    raw = """## Agent Plan

### Scope
Implement dispatch improvements

### Steps
- [S-001] (src/foo.py) Update handler

### CI hints
- pytest tests/test_dispatch.py

### Cross-repo / blast-radius context
Potentially affected repos: ai-sdlc-lab/agent-control-plane
Potentially affected services: ct103-control-plane
Potentially affected tests: tests/test_dispatch.py
Related ADRs: ADR-003-agent-state
missing_graph_edges: (none)

### Confidence
medium

### Recommended next command
/agent fix
"""
    result = parse_plan_output(raw)
    assert result.scope_summary == "Implement dispatch improvements"
    assert result.steps[0].files == ["src/foo.py"]
    assert result.recommended_next_command == "/agent fix"


def test_parse_plan_output_json_coerces_prior_memory_run_ids() -> None:
    payload = {
        "scope_summary": "Plan from prior review memory",
        "steps": [{"id": "S-001", "summary": "Apply review finding", "files": []}],
        "prior_memory_used": [
            "run-d91435838f457716cb443736c4cc3c6b",
            "run-f32dd48059abccc08338352894b886f3",
        ],
    }
    result = parse_plan_output(json.dumps(payload))
    assert len(result.prior_memory_used) == 2
    assert result.prior_memory_used[0].run_id == "run-d91435838f457716cb443736c4cc3c6b"
    assert result.prior_memory_used[0].used_for == "plan_context"


def test_parse_plan_output_json_coerces_prose_blast_radius() -> None:
    payload = {
        "scope_summary": "Plan scope",
        "steps": [{"id": "S-001", "summary": "Step one", "files": []}],
        "blast_radius": "The review should focus on worker idle paths to avoid service disruption.",
    }
    result = parse_plan_output(json.dumps(payload))
    assert result.blast_radius.missing_graph_edges
    assert result.blast_radius.missing_graph_edges[0].startswith("model_narrative:")


def test_parse_plan_output_invalid_raises() -> None:
    with pytest.raises(PlanParseError):
        parse_plan_output("not parseable at all")
