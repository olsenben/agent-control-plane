"""Graph coverage + missing Orbit edge reporting (slice 8a)."""

from __future__ import annotations

from typing import Any

from agent_control.config import Settings, get_settings
from agent_control.graph.provenance import (
    EXTRACTOR_VERSION,
    LANGUAGES_SUPPORTED,
    ORBIT_EDGE_KINDS,
    edge_kind_counts,
    provenance_counts,
)
from agent_control.graph.store import GraphStore


def export_coverage_json(
    repo: str | None = None,
    settings: Settings | None = None,
    *,
    store: GraphStore | None = None,
) -> dict[str, Any]:
    """Report edge-kind / provenance coverage and honest missing Orbit edges."""
    settings = settings or get_settings()
    store = store or GraphStore(settings.graph_db_path)
    store.init_schema()

    if repo and not store.has_repo(repo):
        return {
            "repo": repo,
            "extractor_version": EXTRACTOR_VERSION,
            "languages_supported": list(LANGUAGES_SUPPORTED),
            "edge_kinds": {},
            "provenance_counts": {},
            "files_indexed": 0,
            "files_skipped": 0,
            "source_sha": "",
            "policy_source_sha": "",
            "missing_graph_edges": ["graph snapshot not found for repo"],
            "orbit_edge_kinds_expected": list(ORBIT_EDGE_KINDS),
            "confidence": "low",
        }

    edges = store.list_edges(repo)
    kinds = edge_kind_counts(edges)
    prov = provenance_counts(edges)
    missing: list[str] = []

    # Only flag structural Orbit kinds that a code snapshot should usually produce.
    required_when_snapshot = (
        "repo_contains_file",
        "file_imports_file",
    )
    for kind in required_when_snapshot:
        if kinds.get(kind, 0) == 0:
            missing.append(f"missing_edge_kind:{kind}")

    # Optional SDLC kinds — report as coverage gaps, not hard failures.
    optional = (
        "test_covers_file",
        "adr_constrains_file",
        "adr_constrains_symbol",
        "package_depends_on_package",
        "pipeline_verifies_repo",
        "run_used_memory",
        "run_queried_graph",
    )
    for kind in optional:
        if kinds.get(kind, 0) == 0:
            missing.append(f"coverage_gap:{kind}")

    meta: dict[str, Any] = {}
    if repo:
        meta = store.repo_meta(repo) or {}
    else:
        # Aggregate first repo meta when listing all.
        summary = store.summary()
        meta = {
            "files_indexed": summary.get("files", 0),
            "extractor_version": EXTRACTOR_VERSION,
        }

    return {
        "repo": repo or "*",
        "extractor_version": meta.get("extractor_version") or EXTRACTOR_VERSION,
        "languages_supported": str(meta.get("languages_supported") or "python").split(","),
        "edge_kinds": kinds,
        "provenance_counts": prov,
        "files_indexed": int(meta.get("files_indexed") or 0),
        "files_skipped": int(meta.get("files_skipped") or 0),
        "source_sha": meta.get("source_sha") or "",
        "policy_source_sha": meta.get("policy_source_sha") or "",
        "snapshot_at": meta.get("snapshot_at") or "",
        "edge_count": len(edges),
        "missing_graph_edges": sorted(set(missing)),
        "orbit_edge_kinds_expected": list(ORBIT_EDGE_KINDS),
        "confidence": "medium" if kinds else "low",
    }


def export_edges_json(
    repo: str | None = None,
    *,
    kind: str | None = None,
    provenance: str | None = None,
    settings: Settings | None = None,
    store: GraphStore | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    settings = settings or get_settings()
    store = store or GraphStore(settings.graph_db_path)
    edges = store.list_edges(repo, kind=kind, provenance=provenance)
    truncated = False
    if len(edges) > limit:
        edges = edges[:limit]
        truncated = True
    return {
        "repo": repo or "*",
        "kind_filter": kind,
        "provenance_filter": provenance,
        "extractor_version": EXTRACTOR_VERSION,
        "count": len(edges),
        "truncated": truncated,
        "edge_kinds": edge_kind_counts(edges),
        "provenance_counts": provenance_counts(edges),
        "edges": edges,
    }
