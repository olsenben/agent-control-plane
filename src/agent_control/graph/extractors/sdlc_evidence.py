"""Orbit SDLC / evidence edge extractors (slice 8a)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from agent_control.graph.provenance import annotate_edge

_WORKFLOW_GLOB = ("**/.gitea/workflows/*.yml", "**/.gitea/workflows/*.yaml")
_TEST_NAME_RE = re.compile(r"^test_(.+)$")


def extract_adr_constrain_edges(
    project: str,
    adr_facts: list[dict[str, Any]],
    *,
    known_files: set[str] | None = None,
) -> list[dict[str, str]]:
    """ADR scope.globs / symbols → constrains edges (catalog provenance)."""
    edges: list[dict[str, str]] = []
    known = known_files or set()
    for fact in adr_facts:
        adr_id = str(fact.get("adr_id") or "").strip()
        if not adr_id:
            continue
        adr_node = f"adr:{adr_id}"
        for glob in fact.get("scope_globs") or []:
            path = str(glob).replace("\\", "/").lstrip("./")
            if not path or "*" in path or "?" in path:
                # Keep glob patterns as file nodes so coverage can see them.
                if any(ch in path for ch in "*?["):
                    edges.append(
                        annotate_edge(
                            {
                                "kind": "adr_constrains_file",
                                "src_kind": "adr",
                                "src": adr_node,
                                "dst_kind": "file",
                                "dst": f"file:{path}",
                                "confidence": "medium",
                            },
                            provenance="catalog",
                        )
                    )
                continue
            if known and path not in known:
                # Still record declared constraint; coverage may flag missing file.
                pass
            edges.append(
                annotate_edge(
                    {
                        "kind": "adr_constrains_file",
                        "src_kind": "adr",
                        "src": adr_node,
                        "dst_kind": "file",
                        "dst": f"file:{path}",
                        "confidence": "high" if (not known or path in known) else "medium",
                    },
                    provenance="catalog",
                )
            )
        for symbol in fact.get("scope_symbols") or []:
            sym = str(symbol).strip()
            if not sym:
                continue
            edges.append(
                annotate_edge(
                    {
                        "kind": "adr_constrains_symbol",
                        "src_kind": "adr",
                        "src": adr_node,
                        "dst_kind": "symbol",
                        "dst": f"symbol:{sym}",
                        "confidence": "high",
                    },
                    provenance="catalog",
                )
            )
    return edges


def extract_test_covers_edges(
    project: str,
    *,
    files: list[str],
    tests: list[str],
) -> list[dict[str, str]]:
    """Heuristic test_covers_file edges (inferred provenance)."""
    file_set = {f.replace("\\", "/") for f in files}
    stem_to_files: dict[str, list[str]] = {}
    for path in file_set:
        stem = Path(path).stem
        if stem.startswith("test_"):
            continue
        stem_to_files.setdefault(stem, []).append(path)

    edges: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for test_path in tests:
        rel = test_path.replace("\\", "/")
        stem = Path(rel).stem
        match = _TEST_NAME_RE.match(stem)
        if not match:
            continue
        target_stem = match.group(1)
        for file_path in stem_to_files.get(target_stem, []):
            key = (rel, file_path)
            if key in seen:
                continue
            seen.add(key)
            edges.append(
                annotate_edge(
                    {
                        "kind": "test_covers_file",
                        "src_kind": "test",
                        "src": f"test:{rel}",
                        "dst_kind": "file",
                        "dst": f"file:{file_path}",
                        "confidence": "low",
                    },
                    provenance="inferred",
                )
            )
    return edges


def extract_pipeline_edges(project: str, repo_root: Path) -> list[dict[str, str]]:
    """CI workflow files → pipeline_verifies_repo (static_analysis)."""
    edges: list[dict[str, str]] = []
    workflows: list[Path] = []
    for pattern in _WORKFLOW_GLOB:
        workflows.extend(repo_root.glob(pattern))
    # Also accept flat .gitea/workflows without ** from repo root
    wf_dir = repo_root / ".gitea" / "workflows"
    if wf_dir.is_dir():
        workflows.extend(wf_dir.glob("*.yml"))
        workflows.extend(wf_dir.glob("*.yaml"))

    seen: set[str] = set()
    for path in workflows:
        try:
            rel = path.relative_to(repo_root).as_posix()
        except ValueError:
            continue
        if rel in seen:
            continue
        seen.add(rel)
        edges.append(
            annotate_edge(
                {
                    "kind": "pipeline_verifies_repo",
                    "src_kind": "pipeline",
                    "src": f"pipeline:{rel}",
                    "dst_kind": "repo",
                    "dst": f"repo:{project}",
                    "confidence": "high",
                },
                provenance="static_analysis",
            )
        )
        edges.append(
            annotate_edge(
                {
                    "kind": "test_runs_in_ci_job",
                    "src_kind": "ci_job",
                    "src": f"ci_job:{rel}",
                    "dst_kind": "pipeline",
                    "dst": f"pipeline:{rel}",
                    "confidence": "medium",
                },
                provenance="static_analysis",
            )
        )
    return edges


def extract_event_sdlc_edges(
    project: str,
    *,
    state_root: Path | None,
    memory_db_path: Path | None = None,
    limit: int = 50,
) -> tuple[list[dict[str, str]], list[str]]:
    """Optional event/memory evidence edges. Fail-soft when stores missing."""
    edges: list[dict[str, str]] = []
    warnings: list[str] = []

    if memory_db_path is not None and memory_db_path.is_file():
        try:
            from agent_control.memory.store import MemoryStore

            store = MemoryStore(memory_db_path)
            store.init_schema()
            with store.connect() as conn:
                rows = conn.execute(
                    """
                    SELECT run_id, record_id FROM memory_records
                    WHERE repo_full_name = ?
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (project, limit),
                ).fetchall()
            for row in rows:
                run_id = str(row["run_id"])
                record_id = str(row["record_id"] or run_id)
                edges.append(
                    annotate_edge(
                        {
                            "kind": "run_used_memory",
                            "src_kind": "run",
                            "src": f"run:{run_id}",
                            "dst_kind": "memory",
                            "dst": f"memory:{record_id}",
                            "confidence": "high",
                        },
                        provenance="event",
                    )
                )
        except Exception as exc:  # noqa: BLE001 — fail-soft evidence lane
            warnings.append(f"memory evidence edges skipped: {exc}")

    if state_root is not None and state_root.is_dir():
        try:
            from agent_control.events import load_project_events

            events = load_project_events(state_root, project)
            for ev in events[-limit:]:
                etype = str(ev.get("type") or ev.get("raw_event_type") or "")
                payload = ev.get("payload") or {}
                run_id = str(payload.get("run_id") or "")
                if not run_id:
                    continue
                if etype in ("agent.run_completed", "agent.session_finished") and payload.get(
                    "context_pack"
                ):
                    edges.append(
                        annotate_edge(
                            {
                                "kind": "run_queried_graph",
                                "src_kind": "run",
                                "src": f"run:{run_id}",
                                "dst_kind": "graph_node",
                                "dst": f"graph_node:blast_radius:{project}",
                                "confidence": "medium",
                            },
                            provenance="event",
                        )
                    )
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"event evidence edges skipped: {exc}")

    if not edges:
        warnings.append("no event/memory SDLC evidence edges indexed")
    return edges, warnings
