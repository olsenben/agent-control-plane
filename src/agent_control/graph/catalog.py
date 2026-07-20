"""Parse Backstage-style catalog-info.yaml manifests."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from agent_control.graph.provenance import annotate_edge


@dataclass
class CatalogComponent:
    name: str
    owner: str = ""
    repo: str = ""
    depends_on: list[str] = field(default_factory=list)
    verified_by: list[str] = field(default_factory=list)
    adr_refs: list[str] = field(default_factory=list)
    provides_apis: list[str] = field(default_factory=list)


def find_catalog_file(repo_root: Path) -> Path | None:
    candidates = [
        repo_root / "catalog-info.yaml",
        repo_root / ".agent" / "catalog-info.yaml",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def parse_catalog(path: Path) -> CatalogComponent | None:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if raw.get("kind") != "Component":
        return None
    meta = raw.get("metadata") or {}
    spec = raw.get("spec") or {}
    name = str(meta.get("name", "")).strip()
    if not name:
        return None
    return CatalogComponent(
        name=name,
        owner=str(meta.get("owner", "")),
        repo=str(meta.get("repo", "")),
        depends_on=[str(x) for x in spec.get("dependsOn") or []],
        verified_by=[str(x) for x in spec.get("verifiedBy") or []],
        adr_refs=[str(x) for x in spec.get("adrRefs") or spec.get("adr_refs") or []],
        provides_apis=[str(x) for x in spec.get("providesApis") or []],
    )


def catalog_edges(
    project: str,
    component: CatalogComponent,
) -> list[dict[str, str]]:
    edges: list[dict[str, str]] = []
    svc = f"service:{component.name}"

    for dep in component.depends_on:
        edges.append(
            annotate_edge(
                {
                    "kind": "service_depends_on_service",
                    "src_kind": "service",
                    "src": svc,
                    "dst_kind": "service",
                    "dst": f"service:{dep}",
                    "confidence": "high",
                },
                provenance="catalog",
            )
        )

    for ref in component.verified_by:
        if ref.endswith((".yml", ".yaml")) and ".gitea/workflows" in ref.replace("\\", "/"):
            edges.append(
                annotate_edge(
                    {
                        "kind": "test_runs_in_ci_job",
                        "src_kind": "test",
                        "src": f"test:{ref}",
                        "dst_kind": "ci_job",
                        "dst": f"ci_job:{ref}",
                        "confidence": "high",
                    },
                    provenance="catalog",
                )
            )
            edges.append(
                annotate_edge(
                    {
                        "kind": "service_verified_by",
                        "src_kind": "service",
                        "src": svc,
                        "dst_kind": "ci_job",
                        "dst": f"ci_job:{ref}",
                        "confidence": "high",
                    },
                    provenance="catalog",
                )
            )
        else:
            edges.append(
                annotate_edge(
                    {
                        "kind": "file_tested_by_test",
                        "src_kind": "service",
                        "src": svc,
                        "dst_kind": "test",
                        "dst": f"test:{ref}",
                        "confidence": "high",
                    },
                    provenance="catalog",
                )
            )

    for adr_id in component.adr_refs:
        edges.append(
            annotate_edge(
                {
                    "kind": "adr_mentions_service",
                    "src_kind": "adr",
                    "src": f"adr:{adr_id}",
                    "dst_kind": "service",
                    "dst": svc,
                    "confidence": "high",
                },
                provenance="catalog",
            )
        )
        edges.append(
            annotate_edge(
                {
                    "kind": "adr_constrains_service",
                    "src_kind": "adr",
                    "src": f"adr:{adr_id}",
                    "dst_kind": "service",
                    "dst": svc,
                    "confidence": "high",
                },
                provenance="catalog",
            )
        )

    edges.append(
        annotate_edge(
            {
                "kind": "repo_contains_service",
                "src_kind": "repo",
                "src": f"repo:{project}",
                "dst_kind": "service",
                "dst": svc,
                "confidence": "high",
            },
            provenance="catalog",
        )
    )
    return edges


def ingest_catalog(project: str, repo_root: Path) -> tuple[CatalogComponent | None, list[dict[str, str]]]:
    path = find_catalog_file(repo_root)
    if path is None:
        return None, []
    component = parse_catalog(path)
    if component is None:
        return None, []
    return component, catalog_edges(project, component)
