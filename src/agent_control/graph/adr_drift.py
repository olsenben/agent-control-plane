"""Architecture drift detector: ADR facts vs Orbit graph edges (V5 T04).

Fail-soft: missing ADR dir, missing graph snapshot, or store errors never raise
into the control-plane dispatch path — they become warnings on the report.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_control.adr_compiler import compile_adrs
from agent_control.config import Settings, get_settings
from agent_control.graph.extractors.sdlc_evidence import extract_adr_constrain_edges
from agent_control.graph.store import GraphStore

ADR_DRIFT_EDGE_KINDS = frozenset(
    {
        "adr_constrains_file",
        "adr_constrains_symbol",
    }
)

REPORT_SCHEMA = "adr_drift_report.v1"


def edge_fingerprint(edge: dict[str, Any]) -> tuple[str, str, str]:
    """Stable key for set-diff of ADR constraint edges."""
    return (
        str(edge.get("kind") or ""),
        str(edge.get("src") or ""),
        str(edge.get("dst") or ""),
    )


def _edge_public(edge: dict[str, Any]) -> dict[str, str]:
    return {
        "kind": str(edge.get("kind") or ""),
        "src": str(edge.get("src") or ""),
        "dst": str(edge.get("dst") or ""),
        "src_kind": str(edge.get("src_kind") or ""),
        "dst_kind": str(edge.get("dst_kind") or ""),
    }


def expected_edges_from_adr_facts(
    project: str,
    adr_facts: list[dict[str, Any]],
    *,
    known_files: set[str] | None = None,
) -> list[dict[str, str]]:
    """Compile ADR scope.globs/symbols into expected constraint edges."""
    return extract_adr_constrain_edges(project, adr_facts, known_files=known_files)


def resolve_adr_dir(
    repo: str,
    *,
    adr_dir: Path | None = None,
    local_path: Path | None = None,
    settings: Settings | None = None,
) -> Path | None:
    """Locate docs/adr for a repo; None when unavailable (fail-soft)."""
    if adr_dir is not None:
        return adr_dir if adr_dir.is_dir() else None
    if local_path is not None:
        candidate = local_path / "docs" / "adr"
        return candidate if candidate.is_dir() else None

    settings = settings or get_settings()
    cache = settings.graph_snapshot_cache / repo.replace("/", "__")
    cached = cache / "docs" / "adr"
    if cached.is_dir():
        return cached

    pkg_root = Path(__file__).resolve().parents[3]
    local = pkg_root / "docs" / "adr"
    if repo == "ai-sdlc-lab/agent-control-plane" and local.is_dir():
        return local
    return None


def detect_adr_drift(
    repo: str,
    *,
    adr_dir: Path | None = None,
    local_path: Path | None = None,
    known_files: set[str] | None = None,
    settings: Settings | None = None,
    store: GraphStore | None = None,
    adr_facts: list[dict[str, Any]] | None = None,
    graph_edges: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compare ADR-declared constraint edges to graph store edges.

    Always returns a report dict. Never raises for missing inputs (fail-soft).
    """
    settings = settings or get_settings()
    warnings: list[str] = []
    facts: list[dict[str, Any]] = list(adr_facts) if adr_facts is not None else []

    if adr_facts is None:
        resolved = resolve_adr_dir(
            repo, adr_dir=adr_dir, local_path=local_path, settings=settings
        )
        if resolved is None:
            warnings.append("adr directory not found; expected edges empty")
        else:
            try:
                facts = compile_adrs(resolved)
            except Exception as exc:  # noqa: BLE001 — fail-soft
                warnings.append(f"adr compile skipped: {exc}")
                facts = []

    expected = expected_edges_from_adr_facts(repo, facts, known_files=known_files)
    expected_by_fp = {edge_fingerprint(e): e for e in expected}

    actual_rows: list[dict[str, Any]] = []
    if graph_edges is not None:
        actual_rows = [
            e for e in graph_edges if str(e.get("kind") or "") in ADR_DRIFT_EDGE_KINDS
        ]
    else:
        try:
            store = store or GraphStore(settings.graph_db_path)
            store.init_schema()
            if not store.has_repo(repo):
                warnings.append("graph snapshot not found for repo")
            else:
                for kind in sorted(ADR_DRIFT_EDGE_KINDS):
                    actual_rows.extend(store.list_edges(repo, kind=kind))
        except Exception as exc:  # noqa: BLE001 — fail-soft
            warnings.append(f"graph store read skipped: {exc}")
            actual_rows = []

    actual_by_fp = {edge_fingerprint(e): e for e in actual_rows}

    missing_fps = sorted(set(expected_by_fp) - set(actual_by_fp))
    extra_fps = sorted(set(actual_by_fp) - set(expected_by_fp))

    missing_edges = [_edge_public(expected_by_fp[fp]) for fp in missing_fps]
    extra_edges = [_edge_public(actual_by_fp[fp]) for fp in extra_fps]
    drift = bool(missing_edges or extra_edges)
    risk_tags = ["architecture_drift"] if drift else []

    return {
        "schema": REPORT_SCHEMA,
        "repo": repo,
        "fail_soft": True,
        "ok": True,
        "drift": drift,
        "adr_fact_count": len(facts),
        "expected_count": len(expected_by_fp),
        "actual_count": len(actual_by_fp),
        "missing_edges": missing_edges,
        "extra_edges": extra_edges,
        "missing_count": len(missing_edges),
        "extra_count": len(extra_edges),
        "edge_kinds_compared": sorted(ADR_DRIFT_EDGE_KINDS),
        "warnings": warnings,
        "risk_tags": risk_tags,
    }
