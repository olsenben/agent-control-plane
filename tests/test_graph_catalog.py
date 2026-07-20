"""Tests for catalog-info parser."""

from pathlib import Path

from agent_control.graph.catalog import catalog_edges, parse_catalog


def test_parse_catalog(control_plane_root: Path) -> None:
    component = parse_catalog(control_plane_root / "catalog-info.yaml")
    assert component is not None
    assert component.name == "ct103-control-plane"
    assert "redis-worker-state" in component.depends_on
    assert "tests/test_dispatch.py" in component.verified_by
    assert "ADR-003-agent-state" in component.adr_refs


def test_catalog_edges() -> None:
    from agent_control.graph.catalog import CatalogComponent

    component = CatalogComponent(
        name="demo-svc",
        depends_on=["other-svc"],
        verified_by=["tests/test_foo.py"],
        adr_refs=["ADR-001"],
    )
    edges = catalog_edges("ai-sdlc-lab/demo", component)
    kinds = {e["kind"] for e in edges}
    assert "service_depends_on_service" in kinds
    assert "file_tested_by_test" in kinds
    assert "adr_mentions_service" in kinds
    assert "adr_constrains_service" in kinds
    assert "repo_contains_service" in kinds
    assert all(e.get("provenance") == "catalog" for e in edges)
