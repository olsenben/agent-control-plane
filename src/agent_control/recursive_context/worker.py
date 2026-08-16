"""Conditional recursive context worker (Phase 20 / slice 8c)."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_control.config import Settings, get_settings
from agent_control.project_identity import sanitize_path_segment
from agent_control.recursive_context.config import (
    budget_from_config,
    controller_roles,
    load_recursive_context_config,
    resolve_controller_backend,
)
from agent_control.recursive_context.tools import PrimaryModelFn, ReadOnlyToolBelt, ToolBudget
from agent_control.session.storage import sessions_dir
from agent_shared.models.memory_preflight import MemoryPreflight
from agent_shared.models.recursive_context import (
    SCHEMA_VERSION,
    RecursiveContextBudget,
    RecursiveContextBudgetUsed,
    RecursiveContextResult,
    RecursiveContextSubcall,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _trajectory_path(state_root: Path, project: str, session_id: str) -> Path:
    return (
        sessions_dir(state_root, project)
        / sanitize_path_segment(session_id)
        / "recursive_context_trajectory.jsonl"
    )


def _append_trajectory(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def run_conditional_recursive_context(
    *,
    preflight: MemoryPreflight,
    question: str = "",
    settings: Settings | None = None,
    state_root: Path | None = None,
    primary_model: PrimaryModelFn | None = None,
    force_invoke: bool = False,
    budget: RecursiveContextBudget | None = None,
    controller_backend: str | None = None,
) -> RecursiveContextResult:
    """Invoke 2070-style recursive exploration only when preflight requires it.

    False path: returns recursive_context_result.v1 with skipped=True and never
    constructs a model client. True path: bounded read-only tool loop with
    mandatory evidence citations.

    `controller_backend` selects the V10 T00.5 arm: `deterministic` (C0) keeps
    the allowlisted read-only fallback plan, `model` (C1) additionally routes
    `call_primary_model` to the configured 2070 controller. Unset resolves from
    RECURSIVE_CONTEXT_CONTROLLER_BACKEND and then config/recursive_context.yaml.
    """
    settings = settings or get_settings()
    state_root = state_root or settings.agent_state_root
    cfg = load_recursive_context_config()
    backend = resolve_controller_backend(cfg, settings=settings, override=controller_backend)
    gateway_role, role_label = controller_roles(cfg)
    # Re-validate so budget identity matches RecursiveContextResult's model class
    # (avoids pydantic model_type errors under editable/CI import edges).
    raw_budget = budget if budget is not None else budget_from_config(cfg)
    budget = RecursiveContextBudget.model_validate(raw_budget.model_dump())
    created = _now()
    q = question or _default_question(preflight)
    reasons = list(preflight.invocation_reasons)

    if not force_invoke and not preflight.recursive_context_required:
        return RecursiveContextResult(
            schema_version=SCHEMA_VERSION,
            schema_name=SCHEMA_VERSION,
            session_id=preflight.session_id,
            run_id=preflight.run_id,
            repo=preflight.repo,
            question=q,
            recursive_context_required=False,
            invoked=False,
            skipped=True,
            invocation_reasons=reasons,
            skip_reason=preflight.skip_reason or "deterministic_preflight_sufficient",
            evidence_refs=list(preflight.citations)[:20],
            budget=budget,
            stop_reason="deterministic_preflight_sufficient",
            controller_mode="skipped",
            controller_backend=backend,
            controller_role=gateway_role,
            controller_role_label=role_label,
            created_at=created,
            remaining_uncertainty=list(preflight.uncertainty)[:10],
            recommended_next_evidence=["use_deterministic_preflight"],
        )

    root_cfg = cfg.get("recursive_context") or {}
    if not root_cfg.get("enabled", True):
        return RecursiveContextResult(
            schema_version=SCHEMA_VERSION,
            schema_name=SCHEMA_VERSION,
            session_id=preflight.session_id,
            run_id=preflight.run_id,
            repo=preflight.repo,
            question=q,
            recursive_context_required=True,
            invoked=False,
            skipped=True,
            invocation_reasons=reasons,
            skip_reason="recursive_context_disabled",
            budget=budget,
            stop_reason="policy_denied",
            controller_mode="skipped",
            controller_backend=backend,
            controller_role=gateway_role,
            controller_role_label=role_label,
            created_at=created,
            evidence_refs=["policy:recursive_context.enabled=false"],
        )

    started = time.monotonic()
    traj = _trajectory_path(state_root, preflight.repo, preflight.session_id)
    if traj.is_file():
        traj.unlink()

    from agent_control.recursive_context.model_client import ControllerTelemetry

    telemetry = ControllerTelemetry(backend=backend, role=gateway_role, role_label=role_label)
    builtin_controller = False
    if primary_model is None and backend == "model":
        from agent_control.recursive_context.model_client import build_controller_model_fn

        primary_model = build_controller_model_fn(
            role=gateway_role,
            role_label=role_label,
            project=preflight.repo,
            run_id=preflight.run_id,
            session_id=preflight.session_id,
            budget=budget,
            settings=settings,
            state_root=state_root,
            telemetry=telemetry,
        )
        builtin_controller = True

    tools = ReadOnlyToolBelt(
        project=preflight.repo,
        settings=settings,
        primary_model=primary_model,
        issue_id=preflight.issue_id,
        source_sha=preflight.source_sha,
    )
    tool_budget = ToolBudget(
        max_graph_queries=budget.max_graph_queries,
        max_memory_records=budget.max_memory_records,
        max_subcalls=budget.max_subcalls,
    )

    subcalls: list[RecursiveContextSubcall] = []
    evidence_refs: list[str] = list(preflight.citations)[:20]
    memory_used: list[str] = []
    graph_queries: list[dict[str, Any]] = list(preflight.graph_queries)[:10]
    supported: list[str] = []
    rejected: list[str] = list(preflight.rejected_hypotheses_from_prior_runs)[:10]
    contradictions: list[str] = []
    uncertainty: list[str] = list(preflight.uncertainty)[:10]
    next_evidence: list[str] = []
    stop_reason: str = "sufficient_evidence"
    mode = "deterministic" if primary_model is None else "model_2070"

    plan = _plan_tools(preflight)
    depth = 0
    _append_trajectory(
        traj,
        {
            "event": "start",
            "run_id": preflight.run_id,
            "reasons": reasons,
            "question": q,
            "controller_backend": backend,
            "controller_role": gateway_role,
            "at": created,
        },
    )

    for step in plan:
        if time.monotonic() - started > budget.max_wall_seconds:
            stop_reason = "budget_exhausted"
            break
        if not tool_budget.can_subcall() or len(subcalls) >= tool_budget.max_subcalls:
            stop_reason = "budget_exhausted"
            break
        if depth >= budget.max_depth and step.get("depth", 0) > 0:
            continue

        tool_name = str(step["tool"])
        args = dict(step.get("args") or {})
        # Always pass prior evidence into compare / model calls.
        if tool_name in ("compare_hypotheses", "call_primary_model"):
            args.setdefault("evidence_refs", list(evidence_refs)[:20])
            if tool_name == "compare_hypotheses":
                hyps = list(preflight.rejected_hypotheses_from_prior_runs) or list(
                    preflight.known_failure_modes
                )
                if len(hyps) >= 2:
                    args.setdefault("h1", hyps[0])
                    args.setdefault("h2", hyps[1])
                elif hyps:
                    args.setdefault("h1", hyps[0])
                    args.setdefault("h2", "alternate_unknown")
                else:
                    args.setdefault("h1", "H1_unknown")
                    args.setdefault("h2", "H2_unknown")
            if tool_name == "call_primary_model":
                args.setdefault("question", q)

        result = tools.invoke(tool_name, args, tool_budget)
        if result.summary == "budget_exhausted":
            stop_reason = "budget_exhausted"
            break
        if result.error == "tool not allowed" or result.summary == "policy_denied":
            stop_reason = "policy_denied"
            _append_trajectory(
                traj,
                {
                    "event": "tool",
                    "tool": tool_name,
                    "ok": result.ok,
                    "summary": result.summary,
                    "evidence_refs": result.evidence_refs,
                    "error": result.error,
                },
            )
            break

        depth = max(depth, int(step.get("depth") or 0))
        sub = RecursiveContextSubcall(
            tool=tool_name,
            args={k: v for k, v in args.items() if k != "evidence_refs"},
            evidence_refs=list(result.evidence_refs),
            summary=result.summary[: budget.output_max_chars],
            depth=int(step.get("depth") or 0),
        )
        subcalls.append(sub)
        _append_trajectory(
            traj,
            {
                "event": "tool",
                "tool": tool_name,
                "ok": result.ok,
                "summary": result.summary,
                "evidence_refs": result.evidence_refs,
                "error": result.error,
            },
        )

        for ref in result.evidence_refs:
            if ref not in evidence_refs:
                evidence_refs.append(ref)
            if ref.startswith("memory:") and ref not in memory_used:
                memory_used.append(ref)
            if ref.startswith("graph:") and tool_name.startswith("find"):
                graph_queries.append({"query_kind": tool_name, "ref": ref})

        if tool_name == "compare_hypotheses" and result.ok:
            supported.append(result.summary)
        if tool_name == "get_memory_by_cause" and result.data.get("records"):
            for rec in result.data["records"]:
                cause = rec.get("suspected_root_cause") or ""
                if cause:
                    supported.append(str(cause)[:200])
        if tool_name == "find_affected_tests":
            missing = result.data.get("missing_graph_edges") or []
            if missing:
                uncertainty.append("graph_gaps_in_affected_tests")
                next_evidence.append("refresh_graph_snapshot")

    if builtin_controller and not telemetry.model_invoked:
        # C1 selected but every route failed — fail soft into C0 semantics.
        mode = "fallback_deterministic"
        if stop_reason == "sufficient_evidence":
            stop_reason = "fallback_deterministic"
    elif primary_model is None and mode == "deterministic":
        # Mark fallback when we never had a live 2070 client.
        mode = "fallback_deterministic"
        if stop_reason == "sufficient_evidence":
            stop_reason = "fallback_deterministic"

    if not evidence_refs and root_cfg.get("require_evidence_citations", True):
        uncertainty.append("missing_evidence_citations")
        stop_reason = "human_required"

    # Detect contradiction signal from preflight + tools.
    if "prior_memory_over_budget" in reasons and rejected and supported:
        contradictions.append("prior_hypotheses_compete_with_new_evidence")
        if stop_reason in ("sufficient_evidence", "fallback_deterministic"):
            stop_reason = "contradictory_evidence"

    used = RecursiveContextBudgetUsed(
        depth=depth,
        subcalls=tool_budget.subcalls,
        graph_queries=tool_budget.graph_queries,
        memory_records=tool_budget.memory_records,
        wall_seconds=round(time.monotonic() - started, 3),
        input_tokens=telemetry.prompt_tokens,
        output_tokens=telemetry.completion_tokens,
        tool_calls=len(subcalls),
    )

    try:
        rel_traj = traj.resolve().relative_to(state_root.resolve()).as_posix()
    except ValueError:
        rel_traj = str(traj)

    _append_trajectory(
        traj,
        {
            "event": "stop",
            "stop_reason": stop_reason,
            "budget_used": used.model_dump(),
            **telemetry.as_dict(),
        },
    )

    return RecursiveContextResult(
        schema_version=SCHEMA_VERSION,
        schema_name=SCHEMA_VERSION,
        session_id=preflight.session_id,
        run_id=preflight.run_id,
        repo=preflight.repo,
        question=q,
        recursive_context_required=True,
        invoked=True,
        skipped=False,
        invocation_reasons=reasons,
        graph_queries=graph_queries[:20],
        memory_records_used=memory_used[: budget.max_memory_records],
        subcalls=subcalls,
        supported_hypotheses=supported[:20],
        rejected_hypotheses=rejected,
        contradictions=contradictions,
        remaining_uncertainty=sorted(set(uncertainty))[:20],
        recommended_next_evidence=sorted(set(next_evidence))[:20]
        or (["gather_ci_evidence"] if "graph_coverage_insufficient" in reasons else []),
        evidence_refs=evidence_refs[:100],
        budget=budget,
        budget_used=used,
        stop_reason=stop_reason,  # type: ignore[arg-type]
        controller_mode=mode,  # type: ignore[arg-type]
        controller_backend=backend,
        controller_model_invoked=telemetry.model_invoked,
        controller_role=gateway_role,
        controller_role_label=role_label,
        controller_model_id=telemetry.model_id,
        controller_model_id_source=telemetry.model_id_source,
        controller_provider=telemetry.provider,
        controller_attempts=telemetry.attempts,
        controller_prompt_tokens=telemetry.prompt_tokens,
        controller_completion_tokens=telemetry.completion_tokens,
        controller_wall_seconds=round(telemetry.wall_seconds, 3),
        controller_gpu_seconds=(
            None if telemetry.gpu_seconds is None else round(telemetry.gpu_seconds, 3)
        ),
        controller_data_left_homelab=telemetry.data_left_homelab,
        controller_error_class=telemetry.error_class,
        controller_local_only_enforced=telemetry.local_only_enforced,
        controller_external_routes_refused=telemetry.external_routes_refused,
        controller_route_class=telemetry.route_class,
        controller_endpoint_base_url=telemetry.endpoint_base_url,
        controller_missing_fields=sorted(telemetry.missing_fields),
        trajectory_relative_path=rel_traj,
        created_at=created,
        allow_repo_write=False,
        allow_network=False,
        allow_secret_paths=False,
        require_evidence_citations=bool(root_cfg.get("require_evidence_citations", True)),
    )


def _default_question(preflight: MemoryPreflight) -> str:
    if preflight.invocation_reasons:
        return "Resolve context pressure: " + ", ".join(preflight.invocation_reasons)
    return "Summarize deterministic preflight evidence for dispatch"


def _plan_tools(preflight: MemoryPreflight) -> list[dict[str, Any]]:
    """Deterministic tool plan from invocation reasons (no freeform REPL)."""
    plan: list[dict[str, Any]] = []
    reasons = set(preflight.invocation_reasons)
    files = list(preflight.likely_files)[:5]

    if "graph_coverage_insufficient" in reasons or files:
        plan.append(
            {
                "tool": "find_affected_tests",
                "args": {"files": files or ["src/unknown.py"]},
                "depth": 0,
            }
        )
        if files:
            plan.append(
                {
                    "tool": "find_callers",
                    "args": {"file": files[0]},
                    "depth": 1,
                }
            )
    if "prior_memory_over_budget" in reasons or "multiple_prior_root_causes" in reasons:
        plan.append(
            {
                "tool": "get_memory_by_cause",
                "args": {"cause": "", "issue_id": preflight.issue_id},
                "depth": 0,
            }
        )
        plan.append({"tool": "compare_hypotheses", "args": {}, "depth": 1})
    plan.append({"tool": "search_events", "args": {"query": preflight.run_id}, "depth": 0})
    plan.append({"tool": "get_failure_evidence", "args": {}, "depth": 0})
    if preflight.known_repo_conventions:
        ids = [c.get("adr_id") for c in preflight.known_repo_conventions if c.get("adr_id")]
        plan.append({"tool": "get_adr_facts", "args": {"adr_ids": ids[:5]}, "depth": 0})
    plan.append({"tool": "call_primary_model", "args": {}, "depth": 1})
    return plan
