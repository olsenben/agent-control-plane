"""Read-only typed tools for the recursive context worker (Phase 20).

Forbidden: repo writes, state writes, network (except model role), secrets,
policy decisions, verification claims, freeform SQL/shell.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from agent_control.config import Settings, get_settings
from agent_control.events import load_project_events
from agent_control.graph.blast_radius import compute_blast_radius
from agent_control.graph.store import GraphStore
from agent_control.memory.retrieval import retrieve_prior_memory_dicts
from agent_control.recursive_context.config import allowed_tools, load_recursive_context_config


FORBIDDEN_TOOLS = frozenset(
    {
        "write_repo",
        "write_state",
        "approve",
        "publish",
        "verify",
        "shell",
        "exec",
        "sql",
        "network",
        "secrets",
    }
)


@dataclass
class ToolResult:
    tool: str
    ok: bool
    summary: str
    evidence_refs: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    error: str = ""


PrimaryModelFn = Callable[[str, list[str]], ToolResult]


@dataclass
class ToolBudget:
    max_graph_queries: int
    max_memory_records: int
    max_subcalls: int
    graph_queries: int = 0
    memory_records: int = 0
    subcalls: int = 0

    def can_graph(self) -> bool:
        return self.graph_queries < self.max_graph_queries

    def can_memory(self) -> bool:
        return self.memory_records < self.max_memory_records

    def can_subcall(self) -> bool:
        return self.subcalls < self.max_subcalls


class ReadOnlyToolBelt:
    """Typed CT103 query tools — no mutation authority."""

    def __init__(
        self,
        *,
        project: str,
        settings: Settings | None = None,
        primary_model: PrimaryModelFn | None = None,
        issue_id: int | None = None,
        source_sha: str = "",
    ) -> None:
        self.project = project
        self.settings = settings or get_settings()
        self.primary_model = primary_model
        self.issue_id = issue_id
        self.source_sha = source_sha
        self._cfg = load_recursive_context_config()
        self._allowed = allowed_tools(self._cfg)
        root = self._cfg.get("recursive_context") or {}
        if root.get("allow_repo_write") or root.get("allow_network") or root.get("allow_secret_paths"):
            # Hard fail closed on misconfiguration that enables forbidden capabilities.
            raise RuntimeError("recursive_context config enables forbidden capabilities")

    def invoke(self, tool: str, args: dict[str, Any] | None, budget: ToolBudget) -> ToolResult:
        name = (tool or "").strip()
        args = args or {}
        if name in FORBIDDEN_TOOLS or name not in self._allowed:
            return ToolResult(
                tool=name,
                ok=False,
                summary="policy_denied",
                error=f"tool not allowed: {name}",
                evidence_refs=["policy:recursive_context.allowed_tools"],
            )
        if not budget.can_subcall():
            return ToolResult(
                tool=name,
                ok=False,
                summary="budget_exhausted",
                error="max_subcalls exceeded",
                evidence_refs=["budget:max_subcalls"],
            )
        budget.subcalls += 1
        handler = {
            "search_events": self._search_events,
            "get_run": self._get_run,
            "get_failure_evidence": self._get_failure_evidence,
            "find_callers": self._find_callers,
            "find_references": self._find_references,
            "find_dependency_path": self._find_dependency_path,
            "find_affected_tests": self._find_affected_tests,
            "get_adr_facts": self._get_adr_facts,
            "get_memory_by_cause": self._get_memory_by_cause,
            "compare_hypotheses": self._compare_hypotheses,
            "call_primary_model": self._call_primary_model,
        }.get(name)
        if handler is None:
            return ToolResult(tool=name, ok=False, summary="unknown_tool", error="no handler")
        return handler(args, budget)

    def _search_events(self, args: dict[str, Any], budget: ToolBudget) -> ToolResult:
        events = load_project_events(self.settings.agent_state_root, self.project)
        needle = str(args.get("query") or "").lower()
        matched = []
        for ev in reversed(events[-200:]):
            blob = str(ev).lower()
            if needle and needle not in blob:
                continue
            eid = str(ev.get("event_id") or "")
            if eid:
                matched.append(eid)
            if len(matched) >= 10:
                break
        refs = [f"event:{e}" for e in matched]
        return ToolResult(
            tool="search_events",
            ok=True,
            summary=f"matched {len(matched)} events",
            evidence_refs=refs,
            data={"event_ids": matched},
        )

    def _get_run(self, args: dict[str, Any], budget: ToolBudget) -> ToolResult:
        run_id = str(args.get("run_id") or "")
        events = load_project_events(self.settings.agent_state_root, self.project)
        hits = []
        for ev in events:
            payload = ev.get("payload") or {}
            if str(payload.get("run_id") or "") == run_id:
                hits.append(str(ev.get("event_id") or ""))
        refs = [f"event:{e}" for e in hits if e] or ([f"run:{run_id}"] if run_id else [])
        return ToolResult(
            tool="get_run",
            ok=True,
            summary=f"run {run_id}: {len(hits)} events",
            evidence_refs=refs,
            data={"run_id": run_id, "event_ids": hits},
        )

    def _get_failure_evidence(self, args: dict[str, Any], budget: ToolBudget) -> ToolResult:
        root = self.settings.agent_runs_dir / "ci" / "failure-evidence"
        paths: list[str] = []
        if root.is_dir():
            for p in sorted(root.glob("*/manifest.json"))[:10]:
                paths.append(p.as_posix())
        refs = [f"ci_evidence:{p}" for p in paths] or ["ci_evidence:none"]
        return ToolResult(
            tool="get_failure_evidence",
            ok=True,
            summary=f"{len(paths)} evidence manifests",
            evidence_refs=refs,
            data={"paths": paths},
        )

    def _find_callers(self, args: dict[str, Any], budget: ToolBudget) -> ToolResult:
        return self._graph_file_query("find_callers", args, budget, reverse=True)

    def _find_references(self, args: dict[str, Any], budget: ToolBudget) -> ToolResult:
        return self._graph_file_query("find_references", args, budget, reverse=False)

    def _graph_file_query(
        self,
        tool: str,
        args: dict[str, Any],
        budget: ToolBudget,
        *,
        reverse: bool,
    ) -> ToolResult:
        if not budget.can_graph():
            return ToolResult(
                tool=tool,
                ok=False,
                summary="budget_exhausted",
                error="max_graph_queries exceeded",
                evidence_refs=["budget:max_graph_queries"],
            )
        budget.graph_queries += 1
        path = str(args.get("file") or args.get("path") or "").replace("\\", "/")
        store = GraphStore(self.settings.graph_db_path)
        edges = store.list_edges(self.project)
        node = f"file:{path}" if path and not path.startswith("file:") else path
        related: list[str] = []
        for e in edges:
            if reverse and e.get("dst") == node and e.get("kind") == "file_imports_file":
                related.append(str(e.get("src")))
            elif not reverse and e.get("src") == node:
                related.append(str(e.get("dst")))
        refs = [f"graph:{tool}:{path or 'unknown'}"]
        return ToolResult(
            tool=tool,
            ok=True,
            summary=f"{len(related)} related nodes",
            evidence_refs=refs,
            data={"related": related[:50], "file": path},
        )

    def _find_dependency_path(self, args: dict[str, Any], budget: ToolBudget) -> ToolResult:
        if not budget.can_graph():
            return ToolResult(
                tool="find_dependency_path",
                ok=False,
                summary="budget_exhausted",
                error="max_graph_queries exceeded",
                evidence_refs=["budget:max_graph_queries"],
            )
        budget.graph_queries += 1
        src = str(args.get("src") or "")
        dst = str(args.get("dst") or "")
        return ToolResult(
            tool="find_dependency_path",
            ok=True,
            summary=f"path query {src} -> {dst}",
            evidence_refs=[f"graph:dependency_path:{src}:{dst}"],
            data={"src": src, "dst": dst, "path": [src, dst] if src and dst else []},
        )

    def _find_affected_tests(self, args: dict[str, Any], budget: ToolBudget) -> ToolResult:
        if not budget.can_graph():
            return ToolResult(
                tool="find_affected_tests",
                ok=False,
                summary="budget_exhausted",
                error="max_graph_queries exceeded",
                evidence_refs=["budget:max_graph_queries"],
            )
        budget.graph_queries += 1
        files = args.get("files") or []
        if isinstance(files, str):
            files = [files]
        br = compute_blast_radius(self.project, list(files), settings=self.settings)
        refs = [f"graph:blast_radius:{f}" for f in files[:10]] or ["graph:blast_radius"]
        refs.extend(f"test:{t}" for t in br.affected_tests[:20])
        return ToolResult(
            tool="find_affected_tests",
            ok=True,
            summary=f"{len(br.affected_tests)} affected tests",
            evidence_refs=refs,
            data={
                "affected_tests": list(br.affected_tests),
                "missing_graph_edges": list(br.missing_graph_edges),
            },
        )

    def _get_adr_facts(self, args: dict[str, Any], budget: ToolBudget) -> ToolResult:
        from agent_control.adr_compiler import compile_adrs

        adr_ids = args.get("adr_ids") or []
        if isinstance(adr_ids, str):
            adr_ids = [adr_ids]
        cache = self.settings.graph_snapshot_cache / self.project.replace("/", "__")
        adr_dir = cache / "docs" / "adr"
        facts = compile_adrs(adr_dir) if adr_dir.is_dir() else []
        if adr_ids:
            wanted = {str(a).lower() for a in adr_ids}
            facts = [f for f in facts if str(f.get("adr_id", "")).lower() in wanted]
        refs = [f"adr:{f.get('adr_id')}" for f in facts if f.get("adr_id")]
        return ToolResult(
            tool="get_adr_facts",
            ok=True,
            summary=f"{len(facts)} adr facts",
            evidence_refs=refs or ["adr:none"],
            data={"facts": facts[:20]},
        )

    def _get_memory_by_cause(self, args: dict[str, Any], budget: ToolBudget) -> ToolResult:
        if not budget.can_memory():
            return ToolResult(
                tool="get_memory_by_cause",
                ok=False,
                summary="budget_exhausted",
                error="max_memory_records exceeded",
                evidence_refs=["budget:max_memory_records"],
            )
        cause = str(args.get("cause") or "").lower()
        issue = self.issue_id if self.issue_id is not None else args.get("issue_id")
        records: list[dict[str, Any]] = []
        if issue is not None:
            records = retrieve_prior_memory_dicts(
                self.project,
                int(issue),
                current_target_sha=self.source_sha or None,
                limit=min(10, budget.max_memory_records - budget.memory_records),
                max_chars=20_000,
                settings=self.settings,
            )
        if cause:
            filtered = []
            for r in records:
                blob = str(r).lower()
                if cause in blob:
                    filtered.append(r)
            records = filtered
        budget.memory_records += len(records)
        refs = [f"memory:{r.get('run_id')}" for r in records if r.get("run_id")]
        return ToolResult(
            tool="get_memory_by_cause",
            ok=True,
            summary=f"{len(records)} memory records",
            evidence_refs=refs or ["memory:none"],
            data={"records": records},
        )

    def _compare_hypotheses(self, args: dict[str, Any], budget: ToolBudget) -> ToolResult:
        h1 = str(args.get("h1") or args.get("hypothesis_a") or "")
        h2 = str(args.get("h2") or args.get("hypothesis_b") or "")
        evidence = [str(x) for x in (args.get("evidence_refs") or [])]
        if not evidence:
            return ToolResult(
                tool="compare_hypotheses",
                ok=False,
                summary="require_evidence_citations",
                error="compare_hypotheses requires evidence_refs",
                evidence_refs=[],
            )
        summary = f"compared H1={h1[:80]!r} vs H2={h2[:80]!r} against {len(evidence)} refs"
        return ToolResult(
            tool="compare_hypotheses",
            ok=True,
            summary=summary,
            evidence_refs=evidence,
            data={"h1": h1, "h2": h2, "supported": "inconclusive"},
        )

    def _call_primary_model(self, args: dict[str, Any], budget: ToolBudget) -> ToolResult:
        question = str(args.get("question") or "")
        evidence = [str(x) for x in (args.get("evidence_refs") or [])]
        if not evidence:
            return ToolResult(
                tool="call_primary_model",
                ok=False,
                summary="require_evidence_citations",
                error="call_primary_model requires evidence_refs",
                evidence_refs=[],
            )
        if self.primary_model is not None:
            return self.primary_model(question, evidence)
        # Deterministic fallback — no live 2070 required.
        return ToolResult(
            tool="call_primary_model",
            ok=True,
            summary=f"fallback_deterministic: {question[:120]}",
            evidence_refs=evidence,
            data={"mode": "fallback_deterministic", "question": question},
        )
