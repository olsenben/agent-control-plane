"""Tests for plan output normalization and platform pre-merge."""

import json

from agent_shared.models.context_pack import ContextPack
from agent_shared.models.review import BlastRadiusContext
from agent_workers.rlm.plan_parser import parse_plan_output
from agent_workers.rlm.premerge import premerge_platform_context


def _sample_pack() -> ContextPack:
    return ContextPack(
        project="ai-sdlc-lab/demo-app",
        blast_radius=BlastRadiusContext(
            affected_repos=["ai-sdlc-lab/agent-control-plane"],
            affected_services=["ct103-control-plane"],
            affected_tests=["tests/test_dispatch.py"],
            related_adrs=["ADR-003-agent-state"],
            missing_graph_edges=[],
        ),
        prior_memory=[
            {
                "run_id": "run-d91435838f457716cb443736c4cc3c6b",
                "record_id": "mem-run-d91435838f457716cb443736c4cc3c6b",
            }
        ],
        context_sources=["graph:blast_radius", "memory:prior_review"],
    )


def test_plan_prior_memory_string_list_without_pack() -> None:
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


def test_plan_prose_blast_radius_without_pack() -> None:
    payload = {
        "scope_summary": "Plan scope",
        "steps": [{"id": "S-001", "summary": "Step one", "files": []}],
        "blast_radius": "The review should focus on worker idle paths to avoid service disruption.",
    }
    result = parse_plan_output(json.dumps(payload))
    assert result.blast_radius.missing_graph_edges
    assert result.blast_radius.missing_graph_edges[0].startswith("model_narrative:")


def test_plan_pack_blast_wins_over_model_prose() -> None:
    pack = _sample_pack()
    payload = {
        "scope_summary": "Plan scope",
        "steps": [{"id": "S-001", "summary": "Step one", "files": []}],
        "blast_radius": "Model prose that should be ignored when pack exists.",
    }
    result = parse_plan_output(json.dumps(payload), context_pack=pack)
    assert result.blast_radius.affected_repos == pack.blast_radius.affected_repos
    assert result.blast_radius.affected_tests == pack.blast_radius.affected_tests
    assert not any(edge.startswith("model_narrative:") for edge in result.blast_radius.missing_graph_edges)


def test_plan_pack_prior_memory_wins_over_model_strings() -> None:
    pack = _sample_pack()
    payload = {
        "scope_summary": "Plan scope",
        "steps": [{"id": "S-001", "summary": "Step one", "files": []}],
        "prior_memory_used": ["run-fake-should-not-win"],
    }
    result = parse_plan_output(json.dumps(payload), context_pack=pack)
    assert len(result.prior_memory_used) == 1
    assert result.prior_memory_used[0].run_id == "run-d91435838f457716cb443736c4cc3c6b"
    assert result.prior_memory_used[0].record_id == "mem-run-d91435838f457716cb443736c4cc3c6b"


def test_plan_steps_as_strings_coerced() -> None:
    payload = {
        "scope_summary": "Plan scope",
        "steps": ["Wire dispatch handler", "Add tests"],
    }
    result = parse_plan_output(json.dumps(payload))
    assert len(result.steps) == 2
    assert result.steps[0].id == "S-001"
    assert result.steps[0].summary == "Wire dispatch handler"


def test_premerge_injects_context_sources() -> None:
    pack = _sample_pack()
    merged = premerge_platform_context("plan", {"scope_summary": "x", "steps": []}, pack)
    assert merged["context_sources"] == pack.context_sources
    assert merged["blast_radius"]["affected_repos"] == pack.blast_radius.affected_repos
