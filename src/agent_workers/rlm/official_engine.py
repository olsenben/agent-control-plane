"""Official RLM engine candidate — read-only inspect/explain/review/plan with local model endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_control.model_router import resolve_role_primary
from agent_shared.models.runs import RLMResult
from agent_workers.config.execution_strategy import ExecutionStrategy, get_execution_strategy
from agent_shared.constants import GITEA_COMMENT_SUMMARY_PROMPT_BUDGET_CHARS
from agent_workers.rlm.budget import (
    capped_depth,
    capped_iterations,
    completion_timeout_seconds,
    fit_summary_for_comment,
    truncate_text,
)
from agent_workers.rlm.completion import chat_completion
from agent_workers.rlm.constants import ENGINE_OFFICIAL
from agent_workers.rlm.plan_finalize import finalize_plan_result
from agent_workers.rlm.plan_parser import PlanParseError, parse_plan_output
from agent_workers.rlm.prompts import build_plan_system_preamble, build_review_system_preamble, build_system_preamble
from agent_workers.rlm.review_finalize import finalize_review_result
from agent_workers.rlm.review_parser import ReviewParseError, parse_review_output
from agent_workers.rlm.trace import append_trace_event

INSPECT_KINDS = frozenset({"inspect", "explain"})
REVIEW_KINDS = frozenset({"review"})
PLAN_KINDS = frozenset({"plan"})
READ_ONLY_RISKS = frozenset({"read_only", "read_only_with_repo_context"})


def _context_pack_from_job(job: dict[str, Any]):
    raw = job.get("context_pack")
    if not raw:
        return None
    from agent_shared.models.context_pack import ContextPack

    if isinstance(raw, ContextPack):
        return raw
    return ContextPack.model_validate(raw)


def _has_graph_blast(pack) -> bool:
    if pack is None:
        return False
    br = pack.blast_radius
    return bool(
        br.affected_repos or br.affected_services or br.affected_tests or br.related_adrs
    )


def _has_prior_memory(pack) -> bool:
    return bool(pack is not None and pack.prior_memory)


def _rlms_available() -> bool:
    try:
        import rlm  # noqa: F401

        return True
    except ImportError:
        return False


def gather_read_only_context(
    context_broker: Any,
    *,
    max_files: int,
    max_chars: int,
) -> tuple[str, list[str]]:
    parts: list[str] = []
    sources: list[str] = []
    candidates = ["README.md", "README", "readme.md"]
    for rel in candidates:
        hit = context_broker.read_file(rel, reason="official_rlm_bootstrap")
        if hit.get("blocked") or hit.get("missing"):
            continue
        content = str(hit.get("content") or "")
        if content:
            parts.append(f"--- {rel} ---\n{content}")
            sources.append(rel)
            break

    if len(parts) < max_files:
        workspace: Path = context_broker.workspace
        if workspace.exists():
            for path in sorted(workspace.iterdir()):
                if len(sources) >= max_files:
                    break
                if not path.is_file():
                    continue
                rel = path.name
                if rel.startswith(".") or rel in sources:
                    continue
                hit = context_broker.read_file(rel, reason="official_rlm_context")
                if hit.get("blocked") or hit.get("missing"):
                    continue
                content = str(hit.get("content") or "")
                if not content:
                    continue
                parts.append(f"--- {rel} ---\n{content}")
                sources.append(rel)

    return truncate_text("\n\n".join(parts), max_chars), sources


def _validate_kind_and_risk(kind: str, risk_class: str) -> None:
    if kind in INSPECT_KINDS:
        if risk_class != "read_only":
            raise ValueError(
                f"OfficialRLMEngine supports risk_class read_only for inspect/explain, got {risk_class!r}"
            )
        return
    if kind in REVIEW_KINDS:
        if risk_class != "read_only_with_repo_context":
            raise ValueError(
                "OfficialRLMEngine supports risk_class read_only_with_repo_context for review, "
                f"got {risk_class!r}"
            )
        return
    if kind in PLAN_KINDS:
        if risk_class != "planning_only":
            raise ValueError(
                f"OfficialRLMEngine supports risk_class planning_only for plan, got {risk_class!r}"
            )
        return
    raise ValueError(
        f"OfficialRLMEngine supports read-only inspect/explain/review/plan only, got kind={kind!r}"
    )


def _run_rlms(
    *,
    preamble: str,
    task: str,
    context_text: str,
    endpoint: Any,
    max_iterations: int,
    max_depth: int,
    artifact_dir: str | None,
    run_id: str,
) -> tuple[str, dict[str, Any]]:
    from rlm import RLM

    backend_kwargs = {
        "base_url": endpoint.base_url,
        "model_name": endpoint.model or "llama3",
        "api_key": endpoint.api_key or "ollama",
    }
    rlm = RLM(
        backend="openai",
        backend_kwargs=backend_kwargs,
        max_depth=max_depth,
        max_iterations=max_iterations,
        verbose=False,
        custom_system_prompt=preamble,
    )
    try:
        user_prompt = f"Repository context:\n{context_text}\n\nTask: {task}"
        result = rlm.completion(user_prompt)
        trace = {
            "run_id": run_id,
            "engine": ENGINE_OFFICIAL,
            "mode": "rlms",
            "response_chars": len(result.response),
            "execution_time": result.execution_time,
            "usage": result.usage_summary.to_dict() if hasattr(result.usage_summary, "to_dict") else {},
        }
        append_trace_event(artifact_dir, trace)
        if result.metadata:
            append_trace_event(artifact_dir, {"run_id": run_id, "engine": ENGINE_OFFICIAL, "trajectory": result.metadata})
        return result.response.strip(), trace
    finally:
        close = getattr(rlm, "close", None)
        if callable(close):
            close()


def _run_single_shot(
    *,
    preamble: str,
    task: str,
    context_text: str,
    endpoint: Any,
    artifact_dir: str | None,
    run_id: str,
    timeout_seconds: float,
) -> tuple[str, dict[str, Any]]:
    user_prompt = f"Repository context:\n{context_text}\n\nTask: {task}"
    result = chat_completion(
        endpoint,
        system_prompt=preamble,
        user_prompt=user_prompt,
        max_tokens=1024,
        timeout_seconds=timeout_seconds,
    )
    trace = {
        "run_id": run_id,
        "engine": ENGINE_OFFICIAL,
        "mode": "single_shot_openai_compatible",
        "provider": result.get("provider"),
        "base_url": result.get("base_url"),
        "usage": result.get("usage"),
        "response_chars": len(result.get("content") or ""),
        "timeout_seconds": timeout_seconds,
    }
    append_trace_event(artifact_dir, trace)
    return str(result.get("content") or "").strip(), trace


class OfficialRLMEngine:
    """Candidate engine for read-only inspect/explain/review/plan using rlms or OpenAI-compatible chat."""

    name = ENGINE_OFFICIAL

    def run(
        self,
        job: dict[str, Any],
        workspace: Path,
        policy: dict[str, Any],
        *,
        artifact_dir: str | None = None,
        context_broker: Any | None = None,
        tools: Any | None = None,
        strategy: ExecutionStrategy | None = None,
    ) -> RLMResult:
        strategy = strategy or get_execution_strategy()
        kind = job.get("command_intent", {}).get("kind", "inspect")
        risk_class = str(job.get("risk_class", "read_only"))
        _validate_kind_and_risk(kind, risk_class)

        endpoint = resolve_role_primary("rlm")
        if not endpoint.base_url:
            raise ValueError("OfficialRLMEngine requires configured MODEL_3080_BASE_URL (rlm role endpoint)")

        if kind in REVIEW_KINDS:
            pack = _context_pack_from_job(job)
            preamble = build_review_system_preamble(
                command_scope=job.get("safety", {}).get("command_scope", kind),
                risk_class=risk_class,
                has_graph_blast=_has_graph_blast(pack),
            )
        elif kind in PLAN_KINDS:
            pack = _context_pack_from_job(job)
            preamble = build_plan_system_preamble(
                command_scope=job.get("safety", {}).get("command_scope", kind),
                risk_class=risk_class,
                has_graph_blast=_has_graph_blast(pack),
                has_prior_memory=_has_prior_memory(pack),
            )
        else:
            preamble = build_system_preamble(
                command_scope=job.get("safety", {}).get("command_scope", kind),
                risk_class=risk_class,
            )
        task = job.get("command_intent", {}).get("natural_language_task", "")
        if context_broker is None:
            from agent_workers.context.broker import ContextBroker

            context_broker = ContextBroker(workspace, profile=kind)

        context_text, sources = gather_read_only_context(
            context_broker,
            max_files=strategy.read_only_max_context_files,
            max_chars=strategy.read_only_max_prompt_chars,
        )
        pack = _context_pack_from_job(job)
        if pack is not None:
            from agent_control.graph.context_pack import render_context_pack_text

            pack_text = render_context_pack_text(pack)
            context_text = f"{pack_text}\n\n{context_text}"
            sources = list(pack.context_sources) + sources
        append_trace_event(
            artifact_dir,
            {
                "run_id": job["run_id"],
                "engine": self.name,
                "event": "context_gathered",
                "sources": sources,
                "context_chars": len(context_text),
            },
        )

        max_iterations = capped_iterations(job, strategy.rlms_max_iterations_cap)
        max_depth = capped_depth(job, strategy.rlms_max_depth_cap)
        completion_timeout = completion_timeout_seconds(job)

        if _rlms_available():
            raw_response, _trace = _run_rlms(
                preamble=preamble,
                task=task,
                context_text=context_text,
                endpoint=endpoint,
                max_iterations=max_iterations,
                max_depth=max_depth,
                artifact_dir=artifact_dir,
                run_id=job["run_id"],
            )
            mode_note = "rlms"
        else:
            raw_response, _trace = _run_single_shot(
                preamble=preamble,
                task=task,
                context_text=context_text,
                endpoint=endpoint,
                artifact_dir=artifact_dir,
                run_id=job["run_id"],
                timeout_seconds=completion_timeout,
            )
            mode_note = "single_shot_openai_compatible"

        warnings = list(policy.get("warnings") or [])
        if mode_note == "single_shot_openai_compatible":
            warnings.append("rlms package not installed; used OpenAI-compatible single-shot completion")

        review_result = None
        plan_result = None
        if kind in REVIEW_KINDS:
            try:
                parsed = parse_review_output(raw_response)
            except ReviewParseError as exc:
                raise ValueError(f"Failed to parse review output: {exc}") from exc
            summary, review_result, review_warnings = finalize_review_result(
                parsed,
                known_sources=sources,
                job=job,
                engine=self.name,
            )
            warnings.extend(review_warnings)
        elif kind in PLAN_KINDS:
            try:
                parsed = parse_plan_output(raw_response)
            except PlanParseError as exc:
                raise ValueError(f"Failed to parse plan output: {exc}") from exc
            summary, plan_result, plan_warnings = finalize_plan_result(
                parsed,
                known_sources=sources,
                job=job,
                engine=self.name,
            )
            warnings.extend(plan_warnings)
        else:
            summary = raw_response
            if not summary:
                summary = f"Read-only {kind} completed for '{task}' via {mode_note}; model returned empty content."
            else:
                summary = fit_summary_for_comment(summary, GITEA_COMMENT_SUMMARY_PROMPT_BUDGET_CHARS)

        return RLMResult(
            run_id=job["run_id"],
            session_id=job["session_id"],
            project=job["project"],
            flow=job["flow"],
            agent=job["agent"],
            risk_class=job["risk_class"],
            workflow_definition=job["workflow_definition"],
            flow_config_id=job["flow_config_id"],
            flow_version=job["flow_version"],
            status="completed",
            summary=summary,
            engine=self.name,
            trace_path="rlm_trace.jsonl",
            context_receipt_path="context_receipt.json",
            warnings=warnings,
            review_result=review_result,
            plan_result=plan_result,
        )
