"""Deterministic CT103 memory preflight compiler (Slice 5.5a + 8b Orbit coverage)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_control.adr_compiler import list_related_adrs
from agent_control.config import Settings, get_settings
from agent_control.events import load_project_events
from agent_control.graph.blast_radius import compute_blast_radius
from agent_control.graph.coverage import export_coverage_json
from agent_control.memory.retrieval import retrieve_prior_memory_dicts
from agent_shared.models.agent_session import AgentSession
from agent_shared.models.jobs import TriggerContext
from agent_shared.models.memory_preflight import (
    COMPILER_VERSION,
    MAX_CI_EVIDENCE_POINTERS,
    MAX_CITATIONS,
    MAX_EVIDENCE_EVENT_IDS,
    MAX_EVENTS_SCANNED,
    MAX_KNOWN_FAILURE_MODES,
    MAX_KNOWN_REPO_CONVENTIONS,
    MAX_LIKELY_FILES,
    MAX_MISSING_GRAPH_EDGES,
    MAX_REJECTED_HYPOTHESES,
    MAX_RELEVANT_PRIOR_RUNS,
    MAX_STRING_LEN,
    THRESHOLD_DISTINCT_ROOT_CAUSES,
    THRESHOLD_MISSING_GRAPH_EDGES,
    THRESHOLD_PRIOR_MEMORY,
    ComponentResults,
    HeuristicInputs,
    MemoryPreflight,
)
from agent_shared.models.review import BlastRadiusContext


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clip(text: str, limit: int = MAX_STRING_LEN) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _bound_list(items: list, limit: int) -> tuple[list, bool]:
    if len(items) <= limit:
        return items, False
    return items[:limit], True


def _extract_paths_from_text(text: str) -> list[str]:
    patterns = [
        r"(?:^|\s)([a-zA-Z0-9_./-]+\.py)\b",
        r"(?:^|\s)(src/[a-zA-Z0-9_./-]+)",
    ]
    found: set[str] = set()
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            path = match.group(1).lstrip("./")
            if "/" in path or path.endswith(".py"):
                found.add(path.replace("\\", "/"))
    return sorted(found)


def _safe_under_root(candidate: Path, root: Path) -> bool:
    try:
        resolved = candidate.resolve()
        root_resolved = root.resolve()
        return resolved == root_resolved or root_resolved in resolved.parents
    except OSError:
        return False


def decide_recursive_context(
    *,
    prior_memory_count: int,
    distinct_prior_root_causes: int,
    missing_graph_edge_count: int,
) -> tuple[bool, list[str], str]:
    """Count-based heuristic only — never blocks dispatch; never invokes 2070."""
    reasons: list[str] = []
    if prior_memory_count >= THRESHOLD_PRIOR_MEMORY:
        reasons.append("prior_memory_over_budget")
    if distinct_prior_root_causes >= THRESHOLD_DISTINCT_ROOT_CAUSES:
        reasons.append("multiple_prior_root_causes")
    if missing_graph_edge_count >= THRESHOLD_MISSING_GRAPH_EDGES:
        reasons.append("graph_coverage_insufficient")
    if reasons:
        return True, sorted(set(reasons)), ""
    return False, [], "deterministic_preflight_sufficient"


def compile_memory_preflight(
    *,
    session: AgentSession,
    run_id: str,
    source_sha: str,
    policy_source_sha: str,
    trigger_context: TriggerContext | dict[str, Any],
    settings: Settings | None = None,
    changed_files: list[str] | None = None,
    issue_text: str | None = None,
) -> MemoryPreflight:
    """Compile a bounded deterministic preflight. Component failures → degraded."""
    settings = settings or get_settings()
    if isinstance(trigger_context, dict):
        trigger_context = TriggerContext(**trigger_context)

    project = session.project
    component_results = ComponentResults()
    component_errors: dict[str, str] = {}
    truncated_sections: list[str] = []
    uncertainty: list[str] = []
    staleness: list[str] = []
    citations: list[str] = []

    # --- prior memory ---
    prior_runs: list[dict] = []
    known_failure_modes: list[str] = []
    rejected: list[str] = []
    distinct_causes: set[str] = set()
    try:
        if trigger_context.issue_number is not None:
            prior_runs = retrieve_prior_memory_dicts(
                project,
                trigger_context.issue_number,
                current_target_sha=source_sha,
                command_kind=session.command_kind,
                limit=MAX_RELEVANT_PRIOR_RUNS,
                max_chars=50_000,
                settings=settings,
            )
            # Prefer ci_verified first (stable secondary by run_id).
            prior_runs = sorted(
                prior_runs,
                key=lambda r: (
                    0 if r.get("memory_quality") == "ci_verified" else 1,
                    str(r.get("run_id") or ""),
                ),
            )
            prior_runs, trunc = _bound_list(prior_runs, MAX_RELEVANT_PRIOR_RUNS)
            if trunc:
                truncated_sections.append("relevant_prior_runs")
                component_results = component_results.model_copy(
                    update={"prior_memory": "truncated"}
                )
            for cap in prior_runs:
                if cap.get("is_stale"):
                    staleness.append(_clip(f"stale:{cap.get('run_id')}"))
                rid = str(cap.get("run_id") or "")
                if rid:
                    citations.append(f"memory:{rid}")
                for hyp in cap.get("uncertain_hypotheses") or []:
                    text = _clip(str(hyp))
                    if text:
                        rejected.append(text)
                        distinct_causes.add(text.lower())
                for finding in cap.get("findings") or []:
                    summary = _clip(str(finding.get("summary") or ""))
                    if summary:
                        known_failure_modes.append(summary)
                        distinct_causes.add(summary.lower())
            known_failure_modes, trunc_fm = _bound_list(
                sorted(set(known_failure_modes)), MAX_KNOWN_FAILURE_MODES
            )
            if trunc_fm:
                truncated_sections.append("known_failure_modes")
            rejected, trunc_rj = _bound_list(sorted(set(rejected)), MAX_REJECTED_HYPOTHESES)
            if trunc_rj:
                truncated_sections.append("rejected_hypotheses_from_prior_runs")
        else:
            uncertainty.append("no_issue_number_for_memory_retrieval")
    except Exception as exc:  # noqa: BLE001 — degrade, do not abort
        component_results = component_results.model_copy(update={"prior_memory": "unavailable"})
        component_errors["prior_memory"] = _clip(f"{type(exc).__name__}: {exc}")
        uncertainty.append("prior_memory_unavailable")

    # --- graph / likely files + Orbit coverage (8b) ---
    blast = BlastRadiusContext()
    likely_files: list[str] = []
    graph_queries: list[dict] = []
    missing_edges: list[str] = []
    orbit_coverage: dict[str, Any] = {}
    try:
        files_for_blast = list(changed_files or [])
        if issue_text and not files_for_blast:
            files_for_blast = _extract_paths_from_text(issue_text)
        blast = compute_blast_radius(project, files_for_blast, settings=settings)
        likely_files = sorted(set(files_for_blast))
        likely_files, trunc_lf = _bound_list(likely_files, MAX_LIKELY_FILES)
        if trunc_lf:
            truncated_sections.append("likely_files")
            component_results = component_results.model_copy(update={"graph": "truncated"})
        missing_edges = list(blast.missing_graph_edges)
        graph_queries = [
            {
                "query_kind": "blast_radius",
                "input_files": likely_files[:20],
                "affected_services": list(blast.affected_services)[:20],
                "affected_tests": list(blast.affected_tests)[:20],
            }
        ]
        citations.append("graph:blast_radius")

        # Orbit coverage — fail-soft; gaps feed missing_edges + heuristic.
        try:
            orbit_coverage = export_coverage_json(project, settings=settings)
            coverage_missing = list(orbit_coverage.get("missing_graph_edges") or [])
            missing_edges.extend(coverage_missing)
            graph_queries.append(
                {
                    "query_kind": "coverage",
                    "edge_count": int(orbit_coverage.get("edge_count") or 0),
                    "files_indexed": int(orbit_coverage.get("files_indexed") or 0),
                    "provenance_counts": dict(orbit_coverage.get("provenance_counts") or {}),
                    "missing_count": len(coverage_missing),
                    "extractor_version": orbit_coverage.get("extractor_version") or "",
                    "source_sha": orbit_coverage.get("source_sha") or "",
                }
            )
            citations.append("graph:coverage")
        except Exception as cov_exc:  # noqa: BLE001
            uncertainty.append("graph_coverage_unavailable")
            component_errors["graph_coverage"] = _clip(
                f"{type(cov_exc).__name__}: {cov_exc}"
            )
            if component_results.graph == "complete":
                component_results = component_results.model_copy(update={"graph": "truncated"})

        missing_edges = sorted(set(missing_edges))
        missing_edges, trunc_me = _bound_list(missing_edges, MAX_MISSING_GRAPH_EDGES)
        if trunc_me:
            truncated_sections.append("missing_graph_edges")
            if component_results.graph == "complete":
                component_results = component_results.model_copy(update={"graph": "truncated"})
    except Exception as exc:  # noqa: BLE001
        component_results = component_results.model_copy(update={"graph": "unavailable"})
        component_errors["graph"] = _clip(f"{type(exc).__name__}: {exc}")
        uncertainty.append("graph_unavailable")

    graph_coverage: dict[str, Any] = {
        "affected_services": len(blast.affected_services),
        "affected_tests": len(blast.affected_tests),
        "related_adrs": len(blast.related_adrs),
        "missing_graph_edges": len(missing_edges),
        "likely_files": len(likely_files),
        "edge_count": int(orbit_coverage.get("edge_count") or 0),
        "files_indexed": int(orbit_coverage.get("files_indexed") or 0),
        "files_skipped": int(orbit_coverage.get("files_skipped") or 0),
        "edge_kinds": dict(orbit_coverage.get("edge_kinds") or {}),
        "provenance_counts": dict(orbit_coverage.get("provenance_counts") or {}),
        "extractor_version": orbit_coverage.get("extractor_version") or "",
        "source_sha": orbit_coverage.get("source_sha") or "",
        "confidence": orbit_coverage.get("confidence") or "low",
    }

    # --- ADR / conventions ---
    conventions: list[dict] = []
    try:
        cache_root = settings.graph_snapshot_cache / project.replace("/", "__")
        adr_dir = cache_root / "docs" / "adr"
        if not adr_dir.is_dir():
            pkg_root = Path(__file__).resolve().parents[3]
            if project == "ai-sdlc-lab/agent-control-plane":
                local_adr = pkg_root / "docs" / "adr"
                if local_adr.is_dir():
                    adr_dir = local_adr
        if blast.related_adrs and adr_dir.is_dir():
            conventions = list_related_adrs(adr_dir, blast.related_adrs)
            conventions = sorted(conventions, key=lambda a: str(a.get("adr_id") or ""))
            conventions, trunc_adr = _bound_list(conventions, MAX_KNOWN_REPO_CONVENTIONS)
            if trunc_adr:
                truncated_sections.append("known_repo_conventions")
                component_results = component_results.model_copy(update={"adr": "truncated"})
            for adr in conventions:
                aid = adr.get("adr_id")
                if aid:
                    citations.append(f"adr:{aid}")
        elif not blast.related_adrs:
            uncertainty.append("no_related_adrs_in_blast_radius")
    except Exception as exc:  # noqa: BLE001
        component_results = component_results.model_copy(update={"adr": "unavailable"})
        component_errors["adr"] = _clip(f"{type(exc).__name__}: {exc}")
        uncertainty.append("adr_unavailable")

    # --- events (bounded scan, newest-first) ---
    evidence_event_ids: list[str] = []
    try:
        all_events = load_project_events(settings.agent_state_root, project)
        # Newest-first: reverse stable sort (load is oldest-first by recorded_at, event_id).
        scanned = list(reversed(all_events[-MAX_EVENTS_SCANNED:]))
        if len(all_events) > MAX_EVENTS_SCANNED:
            truncated_sections.append("events_scan")
            component_results = component_results.model_copy(update={"events": "truncated"})

        issue_id = trigger_context.issue_number
        pr_number = trigger_context.pr_number
        matched: list[str] = []
        for ev in scanned:
            payload = ev.get("payload") or {}
            if not isinstance(payload, dict):
                payload = {}
            # Precedence: session → run → issue/PR → source SHA (same issue only).
            sid = payload.get("session_id") or ""
            rid = payload.get("run_id") or ""
            ev_issue = payload.get("issue_id") or payload.get("issue_number")
            ev_pr = payload.get("pr_number") or payload.get("pull_request_number")
            ev_sha = (
                payload.get("head_sha")
                or payload.get("source_sha")
                or payload.get("commit_sha")
                or payload.get("target_sha")
            )
            ok = False
            if sid and sid == session.session_id:
                ok = True
            elif rid and rid == run_id:
                ok = True
            elif issue_id is not None and ev_issue is not None and int(ev_issue) == int(issue_id):
                ok = True
            elif pr_number is not None and ev_pr is not None and int(ev_pr) == int(pr_number):
                ok = True
            elif (
                source_sha
                and ev_sha
                and str(ev_sha) == source_sha
                and issue_id is not None
                and ev_issue is not None
                and int(ev_issue) == int(issue_id)
            ):
                # SHA-only from another issue is not admissible.
                ok = True
            if ok:
                eid = str(ev.get("event_id") or "")
                if eid:
                    matched.append(eid)
        evidence_event_ids = sorted(set(matched))
        evidence_event_ids, trunc_ev = _bound_list(evidence_event_ids, MAX_EVIDENCE_EVENT_IDS)
        if trunc_ev:
            truncated_sections.append("evidence_event_ids")
            if component_results.events == "complete":
                component_results = component_results.model_copy(update={"events": "truncated"})
        for eid in evidence_event_ids:
            citations.append(f"event:{eid}")
    except Exception as exc:  # noqa: BLE001
        component_results = component_results.model_copy(update={"events": "unavailable"})
        component_errors["events"] = _clip(f"{type(exc).__name__}: {exc}")
        uncertainty.append("events_unavailable")

    # --- CI evidence pointers (paths under project-state / artifact root only) ---
    ci_pointers: list[dict] = []
    try:
        artifact_root = Path(settings.agent_runs_dir)
        state_root = Path(settings.agent_state_root)
        evidence_root = artifact_root / "ci" / "failure-evidence"
        # Also allow evidence under agent-state (some deployments nest there).
        state_evidence = state_root / "ci" / "failure-evidence"
        search_roots: list[tuple[Path, Path]] = [(evidence_root, artifact_root)]
        if state_evidence.is_dir():
            search_roots.append((state_evidence, state_root))
        for evidence_root_i, root_i in search_roots:
            if not evidence_root_i.is_dir():
                continue
            for manifest_path in sorted(evidence_root_i.glob("*/manifest.json")):
                if not _safe_under_root(manifest_path, root_i):
                    continue
                if manifest_path.is_symlink():
                    continue
                try:
                    data = json.loads(manifest_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if not isinstance(data, dict):
                    continue
                man_issue = data.get("issue_id")
                man_sha = data.get("commit_sha") or data.get("head_sha")
                if trigger_context.issue_number is not None and man_issue is not None:
                    if int(man_issue) != int(trigger_context.issue_number):
                        continue
                elif source_sha and man_sha and str(man_sha) != source_sha:
                    continue
                elif trigger_context.issue_number is None:
                    continue
                try:
                    rel = manifest_path.resolve().relative_to(root_i.resolve()).as_posix()
                except ValueError:
                    continue
                ci_pointers.append(
                    {
                        "evidence_observation_id": data.get("evidence_observation_id")
                        or manifest_path.parent.name,
                        "relative_path": rel,
                        "commit_sha": man_sha,
                        "failure_fingerprint": data.get("failure_fingerprint"),
                    }
                )
        ci_pointers = sorted(ci_pointers, key=lambda p: str(p.get("evidence_observation_id") or ""))
        ci_pointers, trunc_ci = _bound_list(ci_pointers, MAX_CI_EVIDENCE_POINTERS)
        if trunc_ci:
            truncated_sections.append("ci_evidence_pointers")
            component_results = component_results.model_copy(update={"ci_evidence": "truncated"})
        for ptr in ci_pointers:
            oid = ptr.get("evidence_observation_id")
            if oid:
                citations.append(f"ci_evidence:{oid}")
    except Exception as exc:  # noqa: BLE001
        component_results = component_results.model_copy(update={"ci_evidence": "unavailable"})
        component_errors["ci_evidence"] = _clip(f"{type(exc).__name__}: {exc}")
        uncertainty.append("ci_evidence_unavailable")

    citations, trunc_cit = _bound_list(sorted(set(citations)), MAX_CITATIONS)
    if trunc_cit:
        truncated_sections.append("citations")

    heuristic = HeuristicInputs(
        prior_memory_count=len(prior_runs),
        distinct_prior_root_causes=len(distinct_causes),
        missing_graph_edge_count=len(missing_edges),
    )
    required, reasons, skip = decide_recursive_context(
        prior_memory_count=heuristic.prior_memory_count,
        distinct_prior_root_causes=heuristic.distinct_prior_root_causes,
        missing_graph_edge_count=heuristic.missing_graph_edge_count,
    )

    degraded = any(
        getattr(component_results, field) != "complete"
        for field in ("prior_memory", "graph", "adr", "events", "ci_evidence")
    ) or bool(component_errors)

    recommended: list[str] = []
    if session.command_kind in ("fix", "repair"):
        recommended.append("ci_required_checks")
    elif session.command_kind == "plan":
        recommended.append("human_plan_review")
    else:
        recommended.append("optional_follow_on_plan")

    return MemoryPreflight(
        session_id=session.session_id,
        run_id=run_id,
        repo=session.project,
        issue_id=trigger_context.issue_number,
        pr_number=trigger_context.pr_number,
        source_sha=source_sha,
        policy_source_sha=policy_source_sha or "",
        created_at=_now(),
        compiler_version=COMPILER_VERSION,
        status="degraded" if degraded else "complete",
        recursive_context_required=required,
        invocation_reasons=reasons,
        skip_reason=skip or None,
        decision_summary=(
            "recursive context advisory only; 2070 invoke deferred to 8c"
            if required
            else "deterministic preflight sufficient for dispatch"
        ),
        heuristic_inputs=heuristic,
        component_results=component_results,
        component_errors=component_errors,
        truncated_sections=sorted(set(truncated_sections)),
        relevant_prior_runs=prior_runs,
        known_repo_conventions=conventions,
        likely_files=likely_files,
        known_failure_modes=known_failure_modes,
        rejected_hypotheses_from_prior_runs=rejected,
        graph_queries=graph_queries,
        graph_coverage=graph_coverage,
        missing_graph_edges=missing_edges,
        evidence_event_ids=evidence_event_ids,
        ci_evidence_pointers=ci_pointers,
        uncertainty=sorted(set(uncertainty)),
        staleness=sorted(set(staleness)),
        recommended_verification=recommended,
        citations=citations,
    )
