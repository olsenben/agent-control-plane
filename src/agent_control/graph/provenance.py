"""Orbit-style graph provenance constants and helpers (slice 8a / T05)."""

from __future__ import annotations

from typing import Any, Literal

EXTRACTOR_VERSION = "orbit-8a.1"

EdgeProvenance = Literal[
    "static_analysis",
    "coverage",
    "catalog",
    "event",
    "manual",
    "inferred",
]

PROVENANCE_VALUES: frozenset[str] = frozenset(
    {"static_analysis", "coverage", "catalog", "event", "manual", "inferred"}
)

# Orbit dual-graph edge kinds we expect after an 8a snapshot (code + SDLC/evidence).
ORBIT_EDGE_KINDS: tuple[str, ...] = (
    "repo_contains_file",
    "repo_contains_service",
    "file_imports_file",
    "service_depends_on_service",
    "service_owns_file",
    "file_tested_by_test",
    "test_covers_file",
    "test_runs_in_ci_job",
    "service_verified_by",
    "pipeline_verifies_repo",
    "adr_mentions_service",
    "adr_constrains_service",
    "adr_constrains_file",
    "adr_constrains_symbol",
    "package_depends_on_package",
    "run_used_memory",
    "run_queried_graph",
    # V5 T05 — SARIF security/evidence nodes
    "finding_affects_file",
    "tool_run_produced_finding",
    "tool_run_covers_repo",
)

LANGUAGES_SUPPORTED: tuple[str, ...] = ("python",)


def annotate_edge(
    edge: dict[str, str],
    *,
    provenance: EdgeProvenance,
    confidence: str | None = None,
) -> dict[str, str]:
    """Return a copy of *edge* with Orbit provenance fields."""
    out = dict(edge)
    out["provenance"] = provenance
    if confidence is not None:
        out["confidence"] = confidence
    elif "confidence" not in out:
        out["confidence"] = "medium"
    return out


def annotate_edges(
    edges: list[dict[str, str]],
    *,
    provenance: EdgeProvenance,
) -> list[dict[str, str]]:
    return [annotate_edge(e, provenance=provenance) for e in edges]


def normalize_provenance(value: str | None) -> str:
    if value and value in PROVENANCE_VALUES:
        return value
    return "inferred"


def edge_kind_counts(edges: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for edge in edges:
        kind = str(edge.get("kind") or "")
        if not kind:
            continue
        counts[kind] = counts.get(kind, 0) + 1
    return dict(sorted(counts.items()))


def provenance_counts(edges: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for edge in edges:
        prov = normalize_provenance(edge.get("provenance"))
        counts[prov] = counts.get(prov, 0) + 1
    return dict(sorted(counts.items()))
