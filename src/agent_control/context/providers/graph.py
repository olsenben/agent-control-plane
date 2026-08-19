"""Exact-SHA dependency / test / config graph provider (VExp W1-C).

Default graph is ephemeral (in-memory) from ``snapshot.workspace_path`` using
existing extractors. A ``GraphStore`` is read only after HEAD matches
``target_sha`` *and* ``repos.source_sha`` equals that SHA. SHA mismatch never
reads the store. This wave does not implement ``state_predicate``.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_control.graph.extractors.packages import extract_package_edges
from agent_control.graph.extractors.python_imports import extract_file_import_edges, extract_imports
from agent_control.graph.extractors.sdlc_evidence import extract_test_covers_edges
from agent_control.graph.provenance import annotate_edge
from agent_control.graph.store import GraphStore
from agent_shared.models.context_pack_v2 import EvidenceItem
from agent_shared.models.evidence_query import (
    EvidenceClass,
    EvidenceQuery,
    ProviderResult,
    compute_evidence_item_id,
)
from agent_shared.models.repo_snapshot import RepoSnapshot

PROVIDER_NAME = "graph"
_OWNED_CLASSES: frozenset[EvidenceClass] = frozenset({"dependency_edges", "tests", "config"})
_IMPORT_KIND = "file_imports_file"
_TEST_COVERS_KIND = "test_covers_file"
_FILE_TESTED_KIND = "file_tested_by_test"
_PACKAGE_KIND = "package_depends_on_package"
_TEST_EDGE_KINDS = frozenset({_TEST_COVERS_KIND, _FILE_TESTED_KIND})
_CONFIG_FILENAMES = (
    "pyproject.toml",
    "package.json",
    "setup.cfg",
    "setup.py",
    "requirements.txt",
)
_PATH_IN_TEXT_RE = re.compile(r"(?:^|\s)([A-Za-z0-9_./\\-]+\.py)\b")
_TOKEN_RE = re.compile(r"[A-Za-z_][\w.]*")


def _posix(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def _workspace_head_sha(workspace: Path) -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(workspace), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    sha = out.strip()
    return sha or None


def _normalize_node(node_id: str) -> str:
    raw = _posix(node_id)
    if ":" in raw:
        kind, rest = raw.split(":", 1)
        return f"{kind}:{_posix(rest)}"
    name = Path(raw).name
    if raw.startswith("tests/") or name.startswith("test_"):
        return f"test:{raw}"
    return f"file:{raw}"


def _strip_node(node_id: str) -> str:
    if ":" in node_id:
        return node_id.split(":", 1)[1]
    return node_id


def _edge_key(edge: dict[str, Any]) -> tuple[str, str, str]:
    return (str(edge.get("kind") or ""), str(edge.get("src") or ""), str(edge.get("dst") or ""))


def _module_file_candidates(module: str, path_set: set[str]) -> list[str]:
    parts = module.split(".")
    rel_py = "/".join(parts) + ".py"
    rel_init = "/".join(parts) + "/__init__.py"
    candidates = [rel_py, rel_init, f"src/{rel_py}", f"src/{rel_init}"]
    return [c for c in candidates if c in path_set]


def _src_layout_import_edges(repo_root: Path, files: Sequence[str]) -> list[dict[str, str]]:
    """Resolve imports against the indexed file set, including src-layout paths.

    ``extract_file_import_edges`` maps ``pkg.foo`` to ``pkg/foo.py``, which misses
    files recorded as ``src/pkg/foo.py``. This uses the same ``extract_imports``
    helper against the collected path set.
    """
    path_set = {_posix(f) for f in files}
    edges: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for rel in path_set:
        path = repo_root / rel
        if not path.is_file():
            continue
        for module in extract_imports(path):
            for candidate in _module_file_candidates(module, path_set):
                if candidate == rel:
                    continue
                edge = annotate_edge(
                    {
                        "kind": _IMPORT_KIND,
                        "src_kind": "file",
                        "src": f"file:{rel}",
                        "dst_kind": "file",
                        "dst": f"file:{candidate}",
                        "confidence": "medium",
                    },
                    provenance="static_analysis",
                )
                key = _edge_key(edge)
                if key in seen:
                    break
                seen.add(key)
                edges.append(edge)
                break
    return edges


def _discover_tests(repo_root: Path) -> list[str]:
    tests_dir = repo_root / "tests"
    if not tests_dir.is_dir():
        return []
    found: list[str] = []
    for path in tests_dir.rglob("test_*.py"):
        found.append(path.relative_to(repo_root).as_posix())
    return found


def _discover_config_files(repo_root: Path) -> list[str]:
    return [name for name in _CONFIG_FILENAMES if (repo_root / name).is_file()]


def _merge_edges(*groups: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for group in groups:
        for edge in group:
            key = _edge_key(edge)
            if key in seen or not key[0]:
                continue
            seen.add(key)
            merged.append(dict(edge))
    return merged


@dataclass
class _MemoryGraph:
    files: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    config_files: list[str] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    source: str = "ephemeral"

    def incident(self, node_id: str, kinds: set[str] | None) -> list[dict[str, Any]]:
        hits: list[dict[str, Any]] = []
        for edge in self.edges:
            kind = str(edge.get("kind") or "")
            if kinds is not None and kind not in kinds:
                continue
            if edge.get("src") == node_id or edge.get("dst") == node_id:
                hits.append(edge)
        return hits


def _graph_from_workspace(project: str, repo_root: Path) -> _MemoryGraph:
    py_files, extractor_import_edges, _warnings = extract_file_import_edges(project, repo_root)
    tests = _discover_tests(repo_root)
    config_files = _discover_config_files(repo_root)
    indexed = sorted({_posix(p) for p in [*py_files, *tests]})
    import_edges = _merge_edges(
        extractor_import_edges,
        _src_layout_import_edges(repo_root, indexed),
    )
    covers = extract_test_covers_edges(project, files=py_files, tests=tests)
    packages = extract_package_edges(project, repo_root)
    return _MemoryGraph(
        files=sorted({_posix(p) for p in py_files}),
        tests=sorted({_posix(t) for t in tests}),
        config_files=config_files,
        edges=_merge_edges(import_edges, covers, packages),
        source="ephemeral",
    )


def _graph_from_store_edges(
    edges: Sequence[dict[str, Any]],
    *,
    files: Sequence[str] | None = None,
    tests: Sequence[str] | None = None,
    config_files: Sequence[str] | None = None,
) -> _MemoryGraph:
    file_nodes: set[str] = {_posix(p) for p in files or []}
    test_nodes: set[str] = {_posix(t) for t in tests or []}
    for edge in edges:
        for endpoint, kind in ((edge.get("src"), edge.get("src_kind")), (edge.get("dst"), edge.get("dst_kind"))):
            if not endpoint:
                continue
            path = _strip_node(str(endpoint))
            if kind == "file" or str(endpoint).startswith("file:"):
                file_nodes.add(path)
            elif kind == "test" or str(endpoint).startswith("test:"):
                test_nodes.add(path)
    return _MemoryGraph(
        files=sorted(file_nodes),
        tests=sorted(test_nodes),
        config_files=list(config_files or []),
        edges=[dict(e) for e in edges],
        source="store",
    )


class GraphProvider:
    """Repository-state graph bound to ``RepoSnapshot.target_sha``."""

    def __init__(self, *, store: GraphStore | None = None, repo: str | None = None) -> None:
        self._store = store
        self._repo = repo
        self._graph: _MemoryGraph | None = None
        self._snapshot: RepoSnapshot | None = None

    def neighbors(
        self,
        node_id: str,
        edge_types: Sequence[str] | None,
        depth: int,
    ) -> list[dict[str, Any]]:
        graph = self._graph
        if graph is None or depth < 1:
            return []
        start = _normalize_node(node_id)
        kinds = {k for k in edge_types if k} if edge_types else None
        seen = {start}
        frontier = {start}
        results: list[dict[str, Any]] = []
        for hop in range(1, depth + 1):
            nxt: set[str] = set()
            for node in frontier:
                for edge in graph.incident(node, kinds):
                    src = str(edge.get("src") or "")
                    dst = str(edge.get("dst") or "")
                    other = dst if src == node else src
                    if not other or other in seen:
                        continue
                    seen.add(other)
                    nxt.add(other)
                    results.append(
                        {
                            "node_id": other,
                            "kind": str(edge.get("kind") or ""),
                            "depth": hop,
                        }
                    )
            frontier = nxt
            if not frontier:
                break
        return results

    def affected_tests(self, node_ids: Sequence[str]) -> list[str]:
        graph = self._graph
        if graph is None:
            return []
        tests: set[str] = set()
        normalized = [_normalize_node(n) for n in node_ids]
        for nid in normalized:
            path = _strip_node(nid)
            if nid.startswith("test:") or path in graph.tests:
                tests.add(path)
            for edge in graph.edges:
                kind = str(edge.get("kind") or "")
                if kind not in _TEST_EDGE_KINDS:
                    continue
                src = str(edge.get("src") or "")
                dst = str(edge.get("dst") or "")
                if kind == _TEST_COVERS_KIND and dst == nid:
                    tests.add(_strip_node(src))
                elif kind == _FILE_TESTED_KIND and src == nid:
                    tests.add(_strip_node(dst))
        return sorted(tests)

    def dependency_envelope(self, node_ids: Sequence[str]) -> dict[str, Any]:
        graph = self._graph
        if graph is None:
            return {"nodes": [], "edges": [], "tests": [], "config": []}
        seeds = [_normalize_node(n) for n in node_ids]
        nodes = set(seeds)
        envelope_kinds = {_IMPORT_KIND, _PACKAGE_KIND, *_TEST_EDGE_KINDS}
        collected_edges: list[dict[str, Any]] = []
        seen_keys: set[tuple[str, str, str]] = set()
        for nid in seeds:
            for edge in graph.incident(nid, envelope_kinds):
                key = _edge_key(edge)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                collected_edges.append(edge)
                nodes.add(str(edge.get("src") or ""))
                nodes.add(str(edge.get("dst") or ""))
        for cfg in graph.config_files:
            nodes.add(f"file:{cfg}")
        return {
            "nodes": sorted(n for n in nodes if n),
            "edges": collected_edges,
            "tests": self.affected_tests(seeds),
            "config": list(graph.config_files),
        }

    def query(self, snapshot: RepoSnapshot, request: EvidenceQuery) -> ProviderResult:
        self._graph = None
        self._snapshot = snapshot
        head = _workspace_head_sha(Path(snapshot.workspace_path))
        if head is None or head != snapshot.target_sha:
            return ProviderResult(
                status="error",
                evidence=[],
                diagnostics={
                    "reason": "sha_mismatch",
                    "head": head or "",
                    "target_sha": snapshot.target_sha,
                },
            )
        try:
            graph = self._load_graph(snapshot)
            self._graph = graph
            seeds = self._seed_nodes(request, graph)
            if not seeds:
                seeds = [f"file:{p}" for p in graph.files[:8]]
            wanted = self._wanted_classes(request)
            evidence = self._evidence_for(snapshot, graph, seeds, wanted)
            return ProviderResult(
                status="ok",
                evidence=evidence,
                diagnostics={
                    "graph_source": graph.source,
                    "seed_nodes": seeds,
                },
            )
        except Exception as exc:  # noqa: BLE001 — provider failures stay on ProviderResult
            self._graph = None
            return ProviderResult(
                status="error",
                evidence=[],
                diagnostics={"reason": "provider_failure", "error": str(exc)},
            )

    def _wanted_classes(self, request: EvidenceQuery) -> set[EvidenceClass]:
        if not request.requested_classes:
            return set(_OWNED_CLASSES)
        return {c for c in request.requested_classes if c in _OWNED_CLASSES}

    def _seed_nodes(self, request: EvidenceQuery, graph: _MemoryGraph) -> list[str]:
        seeds: list[str] = []
        seen: set[str] = set()

        def add(node: str) -> None:
            nid = _normalize_node(node)
            if nid in seen:
                return
            seen.add(nid)
            seeds.append(nid)

        for path in request.mentioned_paths:
            if path.strip():
                add(path)
        for match in _PATH_IN_TEXT_RE.finditer(request.query_text or ""):
            add(match.group(1))
        if seeds:
            return seeds
        tokens = {t.lower() for t in _TOKEN_RE.findall(request.query_text or "")}
        if not tokens:
            return []
        for rel in graph.files:
            stem = Path(rel).stem.lower()
            if stem in tokens:
                add(f"file:{rel}")
        for rel in graph.tests:
            stem = Path(rel).stem.lower()
            if stem in tokens:
                add(f"test:{rel}")
        return seeds

    def _load_graph(self, snapshot: RepoSnapshot) -> _MemoryGraph:
        repo_root = Path(snapshot.workspace_path)
        store_graph = self._try_store_graph(snapshot, repo_root)
        if store_graph is not None:
            return store_graph
        return _graph_from_workspace(snapshot.repository_id, repo_root)

    def _try_store_graph(self, snapshot: RepoSnapshot, repo_root: Path) -> _MemoryGraph | None:
        store = self._store
        if store is None:
            return None
        repo = self._repo or snapshot.repository_id
        meta = store.repo_meta(repo)
        if not meta:
            return None
        source_sha = str(meta.get("source_sha") or "")
        if source_sha != snapshot.target_sha:
            return None
        edges = store.list_edges(repo)
        tests = list(store.tests_for_repo(repo)) if hasattr(store, "tests_for_repo") else []
        return _graph_from_store_edges(
            edges,
            tests=tests,
            config_files=_discover_config_files(repo_root),
        )

    def _evidence_for(
        self,
        snapshot: RepoSnapshot,
        graph: _MemoryGraph,
        seeds: Sequence[str],
        wanted: set[EvidenceClass],
    ) -> list[EvidenceItem]:
        items: list[EvidenceItem] = []
        envelope = self.dependency_envelope(seeds)
        if "dependency_edges" in wanted:
            for edge in envelope["edges"]:
                if str(edge.get("kind") or "") != _IMPORT_KIND:
                    continue
                items.append(
                    self._item(
                        snapshot,
                        evidence_type="dependency_edges",
                        source="graph.import",
                        path_or_node=str(edge.get("src") or ""),
                        fact=self._edge_fact(edge),
                        provenance=str(edge.get("provenance") or "static_analysis"),
                    )
                )
        if "tests" in wanted:
            for test_path in envelope["tests"]:
                node = f"test:{test_path}"
                items.append(
                    self._item(
                        snapshot,
                        evidence_type="tests",
                        source="graph.test_covers",
                        path_or_node=node,
                        fact=f"{node} covers {', '.join(seeds)}",
                        provenance="inferred",
                    )
                )
            for edge in envelope["edges"]:
                if str(edge.get("kind") or "") not in _TEST_EDGE_KINDS:
                    continue
                items.append(
                    self._item(
                        snapshot,
                        evidence_type="tests",
                        source="graph.test_covers",
                        path_or_node=str(edge.get("src") or ""),
                        fact=self._edge_fact(edge),
                        provenance=str(edge.get("provenance") or "inferred"),
                    )
                )
        if "config" in wanted:
            for edge in envelope["edges"]:
                if str(edge.get("kind") or "") != _PACKAGE_KIND:
                    continue
                items.append(
                    self._item(
                        snapshot,
                        evidence_type="config",
                        source="graph.config",
                        path_or_node=str(edge.get("src") or ""),
                        fact=self._edge_fact(edge),
                        provenance=str(edge.get("provenance") or "static_analysis"),
                    )
                )
            for cfg in envelope["config"]:
                items.append(
                    self._item(
                        snapshot,
                        evidence_type="config",
                        source="graph.config",
                        path_or_node=cfg,
                        fact=f"config_file:{cfg}",
                        provenance="static_analysis",
                    )
                )
        return self._dedupe_items(items)

    def _item(
        self,
        snapshot: RepoSnapshot,
        *,
        evidence_type: str,
        source: str,
        path_or_node: str,
        fact: str,
        provenance: str,
    ) -> EvidenceItem:
        item_id = compute_evidence_item_id(
            snapshot.snapshot_id,
            PROVIDER_NAME,
            evidence_type,
            path_or_node,
            fact,
        )
        return EvidenceItem(
            text=fact,
            source=source,
            provenance=[provenance],
            id=item_id,
        )

    @staticmethod
    def _edge_fact(edge: dict[str, Any]) -> str:
        return (
            f"{edge.get('src')} -{edge.get('kind')}-> {edge.get('dst')}"
        )

    @staticmethod
    def _dedupe_items(items: list[EvidenceItem]) -> list[EvidenceItem]:
        out: list[EvidenceItem] = []
        seen: set[str] = set()
        for item in items:
            key = item.id or f"{item.source}:{item.text}"
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out
