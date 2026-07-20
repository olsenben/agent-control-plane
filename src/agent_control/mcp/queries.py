"""Read-only query adapters over state projections, graph, and memory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import networkx as nx
import yaml

from agent_control.adr_compiler import compile_adrs, list_related_adrs
from agent_control.config import Settings, get_settings
from agent_control.context_builder import build_context_capsule
from agent_control.events import load_project_events, project_summaries_dir
from agent_control.graph.blast_radius import compute_blast_radius, export_blast_radius_json
from agent_control.graph.store import GraphStore
from agent_control.mcp.bounds import (
    MAX_ADR_FACTS,
    MAX_FINDINGS,
    MAX_LIST_ITEMS,
    MAX_MEMORY_RECORDS,
    MAX_POLICY_CHARS,
    bound_list,
    bound_payload,
    truncate_str,
)
from agent_control.mcp.validate import envelope
from agent_control.memory.retrieval import get_memory_trajectory, record_to_prior_memory_dict
from agent_control.memory.store import MemoryStore
from agent_control.state_reducer import LogicalState
from agent_shared.models.jobs import TriggerContext
from agent_shared.models.state import VerificationState
from agent_shared.repo_identity import normalize_repo_full_name


def _normalize_repo(repo: str) -> str | None:
    return normalize_repo_full_name(repo)


def _adr_dir(repo: str, settings: Settings) -> Path:
    cache = settings.graph_snapshot_cache / repo.replace("/", "__")
    cached = cache / "docs" / "adr"
    if cached.is_dir():
        return cached
    # Local checkout fallback for the control-plane repo itself.
    pkg_root = Path(__file__).resolve().parents[3]
    local = pkg_root / "docs" / "adr"
    if repo == "ai-sdlc-lab/agent-control-plane" and local.is_dir():
        return local
    return cached


def _load_verification_state(repo: str, settings: Settings) -> VerificationState | None:
    path = project_summaries_dir(settings.agent_state_root, repo) / "verification_state.json"
    if not path.is_file():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    return VerificationState.model_validate(raw)


def _build_digraph(edges: list[dict[str, Any]]) -> nx.DiGraph:
    g = nx.DiGraph()
    for edge in edges:
        g.add_edge(edge["src"], edge["dst"], kind=edge.get("kind"))
    return g


def get_context_capsule(repo: str, *, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    normalized = _normalize_repo(repo)
    if normalized is None:
        return envelope(tool="get_context_capsule", ok=False, error="invalid_repo", repo=repo)
    state = _load_verification_state(normalized, settings)
    if state is None:
        state = LogicalState(project=normalized)
    capsule = build_context_capsule(state)
    data = bound_payload(
        {
            "capsule": capsule,
            "source": "verification_state_projection",
        }
    )
    return envelope(
        tool="get_context_capsule",
        ok=True,
        repo=normalized,
        data=data if isinstance(data, dict) else {"capsule": data},
        evidence_refs=[f"state:{normalized}:verification_state"],
    )


def get_relevant_adr_facts(
    repo: str,
    changed_files: list[str] | None = None,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    normalized = _normalize_repo(repo)
    if normalized is None:
        return envelope(tool="get_relevant_adr_facts", ok=False, error="invalid_repo", repo=repo)
    files = [f.replace("\\", "/").lstrip("./") for f in (changed_files or []) if f]
    adr_dir = _adr_dir(normalized, settings)
    if files:
        br = compute_blast_radius(normalized, files, settings=settings)
        facts = list_related_adrs(adr_dir, br.related_adrs) if br.related_adrs else []
        if not facts and adr_dir.is_dir():
            facts = compile_adrs(adr_dir)
    else:
        facts = compile_adrs(adr_dir) if adr_dir.is_dir() else []
    facts = bound_list(facts, MAX_ADR_FACTS)
    data = bound_payload(
        {
            "changed_files": bound_list(files),
            "facts": facts,
            "count": len(facts),
        }
    )
    refs = [f"adr:{f.get('adr_id')}" for f in facts if isinstance(f, dict) and f.get("adr_id")]
    return envelope(
        tool="get_relevant_adr_facts",
        ok=True,
        repo=normalized,
        data=data if isinstance(data, dict) else {"facts": []},
        evidence_refs=refs or ["adr:none"],
    )


def get_finding(
    repo: str,
    finding_id: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    normalized = _normalize_repo(repo)
    if normalized is None:
        return envelope(tool="get_finding", ok=False, error="invalid_repo", repo=repo)
    if not finding_id.strip():
        return envelope(
            tool="get_finding",
            ok=False,
            error="finding_id_required",
            repo=normalized,
        )
    store = MemoryStore(settings.memory_db_path)
    store.init_schema()
    needle = finding_id.strip()
    with store.connect() as conn:
        rows = conn.execute(
            """
            SELECT record_json FROM memory_records
            WHERE repo_full_name = ?
            ORDER BY created_at DESC LIMIT 200
            """,
            (normalized,),
        ).fetchall()
    for row in rows:
        record = json.loads(row["record_json"])
        for finding in record.get("findings") or []:
            if str(finding.get("id") or "") == needle:
                projected = {
                    "schema": "agent.finding.v1",
                    "finding_id": finding.get("id"),
                    "summary": truncate_str(str(finding.get("summary") or "")),
                    "severity": finding.get("severity"),
                    "file": finding.get("file"),
                    "confidence": finding.get("confidence"),
                    "risk_tags": bound_list(list(finding.get("risk_tags") or [])),
                    "run_id": record.get("run_id"),
                    "source_command": record.get("source_command"),
                    "epistemic_status": record.get("epistemic_status") or "inferred",
                }
                return envelope(
                    tool="get_finding",
                    ok=True,
                    repo=normalized,
                    data={"finding": projected},
                    evidence_refs=[
                        f"memory:{record.get('run_id')}",
                        f"finding:{needle}",
                    ],
                )
    return envelope(
        tool="get_finding",
        ok=False,
        error="finding_not_found",
        repo=normalized,
        evidence_refs=[f"finding:{needle}"],
    )


def get_verification_state(repo: str, *, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    normalized = _normalize_repo(repo)
    if normalized is None:
        return envelope(tool="get_verification_state", ok=False, error="invalid_repo", repo=repo)
    state = _load_verification_state(normalized, settings)
    if state is None:
        return envelope(
            tool="get_verification_state",
            ok=False,
            error="verification_state_missing",
            repo=normalized,
            evidence_refs=[f"state:{normalized}:verification_state"],
        )
    dumped = state.model_dump(mode="json")
    # Bound nested blobs that can grow large.
    if isinstance(dumped.get("issue_state"), dict):
        body = dumped["issue_state"].get("body")
        if isinstance(body, str):
            dumped["issue_state"]["body"] = truncate_str(body)
    data = bound_payload({"state": dumped})
    return envelope(
        tool="get_verification_state",
        ok=True,
        repo=normalized,
        data=data if isinstance(data, dict) else {"state": {}},
        evidence_refs=[f"state:{normalized}:verification_state"],
    )


_POLICY_ALLOWLIST = frozenset(
    {
        "tools",
        "recursive_context",
        "command_registry",
        "adequacy_profiles",
        "projects",
    }
)


def get_policy(
    repo: str,
    policy_name: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    normalized = _normalize_repo(repo)
    if normalized is None:
        return envelope(tool="get_policy", ok=False, error="invalid_repo", repo=repo)
    name = policy_name.strip().removesuffix(".yaml").removesuffix(".yml")
    if name not in _POLICY_ALLOWLIST:
        return envelope(
            tool="get_policy",
            ok=False,
            error="policy_not_allowlisted",
            repo=normalized,
            data={"allowed": sorted(_POLICY_ALLOWLIST)},
        )
    pkg_root = Path(__file__).resolve().parents[3]
    candidates = [
        pkg_root / "config" / f"{name}.yaml",
        pkg_root / ".agent" / "policies" / f"{name}.yaml",
        settings.graph_snapshot_cache / normalized.replace("/", "__") / ".agent" / "policies" / f"{name}.yaml",
    ]
    path: Path | None = next((p for p in candidates if p.is_file()), None)
    if path is None:
        return envelope(
            tool="get_policy",
            ok=False,
            error="policy_not_found",
            repo=normalized,
            data={"policy_name": name},
        )
    text = truncate_str(path.read_text(encoding="utf-8"), MAX_POLICY_CHARS)
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError:
        parsed = None
    return envelope(
        tool="get_policy",
        ok=True,
        repo=normalized,
        data={
            "policy_name": name,
            "path": str(path),
            "content": text,
            "parsed": parsed if isinstance(parsed, (dict, list)) else None,
        },
        evidence_refs=[f"policy:{name}"],
    )


def get_run_trajectory(
    repo: str,
    run_id: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    normalized = _normalize_repo(repo)
    if normalized is None:
        return envelope(tool="get_run_trajectory", ok=False, error="invalid_repo", repo=repo)
    if not run_id.strip():
        return envelope(
            tool="get_run_trajectory",
            ok=False,
            error="run_id_required",
            repo=normalized,
        )
    rid = run_id.strip()
    store = MemoryStore(settings.memory_db_path)
    record = store.get_by_run_id(rid)
    memory_blob: dict[str, Any] | None = None
    if record is not None and record.repo_full_name == normalized:
        memory_blob = record_to_prior_memory_dict(record)

    events = load_project_events(settings.agent_state_root, normalized)
    event_ids: list[str] = []
    for ev in events:
        payload = ev.get("payload") or {}
        if str(payload.get("run_id") or "") == rid or str(ev.get("run_id") or "") == rid:
            eid = str(ev.get("event_id") or "")
            if eid:
                event_ids.append(eid)
            if len(event_ids) >= MAX_LIST_ITEMS:
                break

    # Optional recursive-context trajectory file under sessions.
    traj_lines: list[dict[str, Any]] = []
    sessions_root = settings.agent_state_root / "projects" / normalized.split("/")[0] / normalized.split("/")[1] / "sessions"
    if sessions_root.is_dir():
        for path in sessions_root.glob("*/recursive_context_trajectory.jsonl"):
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    if rid in line:
                        traj_lines.append(json.loads(line))
                        if len(traj_lines) >= MAX_LIST_ITEMS:
                            break
            except (OSError, json.JSONDecodeError):
                continue
            if len(traj_lines) >= MAX_LIST_ITEMS:
                break

    if memory_blob is None and not event_ids and not traj_lines:
        return envelope(
            tool="get_run_trajectory",
            ok=False,
            error="run_not_found",
            repo=normalized,
            evidence_refs=[f"run:{rid}"],
        )

    data = bound_payload(
        {
            "run_id": rid,
            "memory": memory_blob,
            "event_ids": bound_list(event_ids),
            "recursive_trajectory": bound_list(traj_lines),
        }
    )
    return envelope(
        tool="get_run_trajectory",
        ok=True,
        repo=normalized,
        data=data if isinstance(data, dict) else {"run_id": rid},
        evidence_refs=[f"run:{rid}"] + [f"event:{e}" for e in event_ids[:10]],
    )


def find_callers(
    repo: str,
    file: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    normalized = _normalize_repo(repo)
    if normalized is None:
        return envelope(tool="find_callers", ok=False, error="invalid_repo", repo=repo)
    path = file.replace("\\", "/").lstrip("./")
    store = GraphStore(settings.graph_db_path)
    edges = store.list_edges(normalized) if store.has_repo(normalized) else []
    node = f"file:{path}" if not path.startswith("file:") else path
    related: list[str] = []
    for e in edges:
        if e.get("dst") == node and e.get("kind") == "file_imports_file":
            related.append(str(e.get("src")))
            if len(related) >= MAX_LIST_ITEMS:
                break
    return envelope(
        tool="find_callers",
        ok=True,
        repo=normalized,
        data={"file": path, "related": related, "count": len(related)},
        evidence_refs=[f"graph:find_callers:{path}"],
    )


def find_affected_tests(
    repo: str,
    files: list[str] | None = None,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    normalized = _normalize_repo(repo)
    if normalized is None:
        return envelope(tool="find_affected_tests", ok=False, error="invalid_repo", repo=repo)
    file_list = [f.replace("\\", "/").lstrip("./") for f in (files or []) if f]
    br = compute_blast_radius(normalized, file_list, settings=settings)
    tests = bound_list(list(br.affected_tests))
    return envelope(
        tool="find_affected_tests",
        ok=True,
        repo=normalized,
        data={
            "files": bound_list(file_list),
            "affected_tests": tests,
            "missing_graph_edges": bound_list(list(br.missing_graph_edges)),
        },
        evidence_refs=["graph:blast_radius"] + [f"test:{t}" for t in tests[:20]],
    )


def find_dependency_path(
    repo: str,
    src: str,
    dst: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    normalized = _normalize_repo(repo)
    if normalized is None:
        return envelope(tool="find_dependency_path", ok=False, error="invalid_repo", repo=repo)
    src_n = src if ":" in src else f"file:{src.replace(chr(92), '/').lstrip('./')}"
    dst_n = dst if ":" in dst else f"file:{dst.replace(chr(92), '/').lstrip('./')}"
    store = GraphStore(settings.graph_db_path)
    path_nodes: list[str] = []
    error = ""
    if not store.has_repo(normalized):
        error = "graph_snapshot_missing"
    else:
        edges = store.list_edges(normalized)
        g = _build_digraph(edges)
        if src_n not in g or dst_n not in g:
            error = "node_not_in_graph"
        else:
            try:
                path_nodes = [str(n) for n in nx.shortest_path(g, src_n, dst_n)]
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                error = "no_path"
    data = {
        "src": src_n,
        "dst": dst_n,
        "path": bound_list(path_nodes),
        "length": max(0, len(path_nodes) - 1) if path_nodes else 0,
    }
    return envelope(
        tool="find_dependency_path",
        ok=not error,
        repo=normalized,
        data=data,
        error=error,
        evidence_refs=[f"graph:dependency_path:{src_n}:{dst_n}"],
    )


def explain_blast_radius(
    repo: str,
    changed_files: list[str] | None = None,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    normalized = _normalize_repo(repo)
    if normalized is None:
        return envelope(tool="explain_blast_radius", ok=False, error="invalid_repo", repo=repo)
    files = [f.replace("\\", "/").lstrip("./") for f in (changed_files or []) if f]
    exported = export_blast_radius_json(normalized, files, settings=settings)
    # Bound large list fields.
    for key in ("affected_services", "affected_tests", "related_adrs", "missing_edges", "changed_files"):
        if key in exported and isinstance(exported[key], list):
            exported[key] = bound_list(exported[key])
    data = bound_payload(exported)
    return envelope(
        tool="explain_blast_radius",
        ok=True,
        repo=normalized,
        data=data if isinstance(data, dict) else {"blast_radius": data},
        evidence_refs=[f"graph:blast_radius:{normalized}"],
    )


def get_context_pack(
    repo: str,
    *,
    changed_files: list[str] | None = None,
    issue_id: int | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Bounded local context pack — no Gitea network; projections + graph + memory only."""
    settings = settings or get_settings()
    normalized = _normalize_repo(repo)
    if normalized is None:
        return envelope(tool="get_context_pack", ok=False, error="invalid_repo", repo=repo)
    files = [f.replace("\\", "/").lstrip("./") for f in (changed_files or []) if f]
    br = compute_blast_radius(normalized, files, settings=settings)
    adr_dir = _adr_dir(normalized, settings)
    adr_slice = list_related_adrs(adr_dir, br.related_adrs) if br.related_adrs else []
    adr_slice = bound_list(adr_slice, MAX_ADR_FACTS)

    prior_memory: list[dict[str, Any]] = []
    if issue_id is not None:
        records = get_memory_trajectory(normalized, issue_id, limit=MAX_MEMORY_RECORDS, settings=settings)
        prior_memory = [record_to_prior_memory_dict(r) for r in records[:MAX_MEMORY_RECORDS]]
        for cap in prior_memory:
            if "findings" in cap and isinstance(cap["findings"], list):
                cap["findings"] = bound_list(cap["findings"], MAX_FINDINGS)

    pack = {
        "schema": "context_pack.v1",
        "project": normalized,
        "issue_number": issue_id,
        "changed_files": bound_list(files),
        "blast_radius": br.model_dump(mode="json"),
        "adr_slice": adr_slice,
        "prior_memory": prior_memory,
        "context_sources": [
            "graph_blast_radius",
            *(["adr_compiler"] if adr_slice else []),
            *(["memory_retrieval"] if prior_memory else []),
        ],
        "trigger": TriggerContext(
            event_type="mcp.read",
            issue_number=issue_id,
        ).model_dump(mode="json"),
        "network": False,
    }
    data = bound_payload(pack)
    return envelope(
        tool="get_context_pack",
        ok=True,
        repo=normalized,
        data=data if isinstance(data, dict) else {"pack": data},
        evidence_refs=[f"graph:context_pack:{normalized}"],
    )
