"""Blast-radius computation via NetworkX."""

from __future__ import annotations

from typing import Any

import networkx as nx

from agent_control.config import Settings, get_settings
from agent_control.graph.store import GraphStore
from agent_shared.models.review import BlastRadiusContext


def _strip_prefix(node_id: str) -> str:
    if ":" in node_id:
        return node_id.split(":", 1)[1]
    return node_id


def _build_digraph(edges: list[dict[str, Any]]) -> nx.DiGraph:
    g = nx.DiGraph()
    for edge in edges:
        g.add_edge(edge["src"], edge["dst"], kind=edge["kind"])
    return g


def _rdeps_files(g: nx.DiGraph, changed_files: list[str]) -> set[str]:
    affected: set[str] = set(changed_files)
    for rel in changed_files:
        node = f"file:{rel}"
        if node not in g:
            continue
        for pred in nx.ancestors(g, node):
            if pred.startswith("file:"):
                affected.add(_strip_prefix(pred))
    return affected


def _services_for_files(g: nx.DiGraph, files: set[str]) -> set[str]:
    services: set[str] = set()
    for rel in files:
        file_node = f"file:{rel}"
        for pred in g.predecessors(file_node) if file_node in g else []:
            if pred.startswith("service:"):
                services.add(_strip_prefix(pred))
        for succ in g.successors(file_node) if file_node in g else []:
            if succ.startswith("service:"):
                services.add(_strip_prefix(succ))
    for node in g.nodes:
        if node.startswith("service:"):
            services.add(_strip_prefix(node))
    return services


def _related_services(g: nx.DiGraph, seeds: set[str]) -> set[str]:
    related = set(seeds)
    for svc in list(seeds):
        node = f"service:{svc}"
        if node not in g:
            continue
        for pred in nx.ancestors(g, node):
            if pred.startswith("service:"):
                related.add(_strip_prefix(pred))
        for succ in nx.descendants(g, node):
            if succ.startswith("service:"):
                related.add(_strip_prefix(succ))
    return related


def _tests_for_services(g: nx.DiGraph, services: set[str]) -> set[str]:
    tests: set[str] = set()
    for svc in services:
        svc_node = f"service:{svc}"
        if svc_node not in g:
            continue
        for succ in g.successors(svc_node):
            if succ.startswith("test:"):
                tests.add(_strip_prefix(succ))
    for edge in g.edges(data=True):
        src, dst, data = edge
        if data.get("kind") == "file_tested_by_test" and dst.startswith("test:"):
            tests.add(_strip_prefix(dst))
    return tests


def _adrs_for_services(g: nx.DiGraph, services: set[str]) -> set[str]:
    adrs: set[str] = set()
    for svc in services:
        svc_node = f"service:{svc}"
        for pred in g.predecessors(svc_node) if svc_node in g else []:
            if pred.startswith("adr:"):
                adrs.add(_strip_prefix(pred))
    return adrs


def compute_blast_radius(
    repo: str,
    changed_files: list[str],
    settings: Settings | None = None,
    *,
    store: GraphStore | None = None,
) -> BlastRadiusContext:
    settings = settings or get_settings()
    store = store or GraphStore(settings.graph_db_path)
    missing: list[str] = []

    if not store.has_repo(repo):
        missing.append("graph snapshot not found for repo")
        return BlastRadiusContext(missing_graph_edges=missing)

    edges = store.list_edges(repo)
    if not edges:
        missing.append("no edges indexed for repo")
        return BlastRadiusContext(missing_graph_edges=missing)

    g = _build_digraph(edges)
    normalized = [f.replace("\\", "/").lstrip("./") for f in changed_files if f]
    if not normalized:
        missing.append("no changed files provided")

    affected_files = _rdeps_files(g, normalized) if normalized else set()
    services = _related_services(g, _services_for_files(g, affected_files))
    if not services and store.services_for_repo(repo):
        services = set(store.services_for_repo(repo))

    tests = _tests_for_services(g, services)
    if not tests:
        for t in store.tests_for_repo(repo):
            tests.add(t)

    adrs = _adrs_for_services(g, services)
    if not adrs:
        for a in store.adrs_for_repo(repo):
            adrs.add(a)

    if not store.services_for_repo(repo):
        missing.append("no catalog-info service for repo")

    for rel in normalized:
        if f"file:{rel}" not in g:
            missing.append(f"file not in graph: {rel}")

    return BlastRadiusContext(
        affected_repos=[repo] if affected_files or services else [],
        affected_services=sorted(services),
        affected_tests=sorted(tests),
        related_adrs=sorted(adrs),
        missing_graph_edges=sorted(set(missing)),
    )


def export_blast_radius_json(
    repo: str,
    changed_files: list[str],
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    store = GraphStore(settings.graph_db_path)
    br = compute_blast_radius(repo, changed_files, settings=settings, store=store)
    meta = store.repo_meta(repo) or {}
    edges = store.list_edges(repo) if store.has_repo(repo) else []
    from agent_control.graph.provenance import (
        EXTRACTOR_VERSION,
        edge_kind_counts,
        provenance_counts,
    )

    return {
        "repo": repo,
        "changed_files": changed_files,
        "affected_services": br.affected_services,
        "affected_repos": br.affected_repos,
        "affected_tests": br.affected_tests,
        "related_adrs": br.related_adrs,
        "missing_edges": br.missing_graph_edges,
        "confidence": "medium" if br.affected_services else "low",
        "source_sha": meta.get("source_sha") or "",
        "extractor_version": meta.get("extractor_version") or EXTRACTOR_VERSION,
        "edge_kinds": edge_kind_counts(edges),
        "provenance_counts": provenance_counts(edges),
        "fail_soft": True,
    }
