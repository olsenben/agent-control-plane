"""Official RLM engine candidate — read-only inspect/explain/review/plan with local model endpoints."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from agent_workers.rlm.quality_loop import run_quality_gated_attempts
from agent_workers.rlm.model_routing import resolve_rlm_gpu_endpoint, to_control_plane_endpoint
from agent_shared.models.fix import FixResult
from agent_shared.models.plan import PlanResult
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
from agent_workers.rlm.fix_finalize import finalize_fix_result
from agent_workers.rlm.fix_parser import FixParseError, parse_fix_output
from agent_workers.rlm.model_output import StructuredParseFailure
from agent_workers.rlm.plan_finalize import finalize_plan_result
from agent_workers.rlm.plan_parser import PlanParseError, parse_plan_output
from agent_workers.rlm.prompts import (
    build_fix_system_preamble,
    build_plan_system_preamble,
    build_review_system_preamble,
    build_system_preamble,
)
from agent_workers.rlm.review_finalize import finalize_review_result
from agent_workers.rlm.review_parser import ReviewParseError, parse_review_output
from agent_workers.rlm.trace import append_trace_event
from agent_workers.artifacts.writer import write_json

INSPECT_KINDS = frozenset({"inspect", "explain"})
REVIEW_KINDS = frozenset({"review"})
PLAN_KINDS = frozenset({"plan"})
FIX_KINDS = frozenset({"fix"})
READ_ONLY_RISKS = frozenset({"read_only", "read_only_with_repo_context"})


SCHEMA_VERSION_V1 = "context_pack.v1"
SCHEMA_VERSION_V2 = "context-pack.v2"


def _schema_version_of(raw: Any) -> str | None:
    if raw is None:
        return None
    version = getattr(raw, "schema_version", None)
    if version:
        return str(version)
    if isinstance(raw, dict):
        value = raw.get("schema_version")
        return str(value) if value else None
    return None


def _is_v2_pack(pack: Any) -> bool:
    return _schema_version_of(pack) == SCHEMA_VERSION_V2


def _context_pack_from_job(job: dict[str, Any]):
    """Load a discriminated v1/v2 pack. Do not coerce V2 into ContextPack."""
    raw = job.get("context_pack")
    if not raw:
        return None
    from agent_shared.models.context_pack import ContextPack
    from agent_shared.models.context_pack_v2 import ContextPackV2

    if isinstance(raw, ContextPackV2):
        return raw
    if isinstance(raw, ContextPack):
        return raw
    schema = _schema_version_of(raw)
    if schema == SCHEMA_VERSION_V2:
        return ContextPackV2.model_validate(raw)
    if schema in (None, SCHEMA_VERSION_V1):
        return ContextPack.model_validate(raw)
    raise ValueError(f"unsupported context_pack schema_version: {schema!r}")


def _has_graph_blast(pack) -> bool:
    if pack is None or _is_v2_pack(pack):
        return False
    br = pack.blast_radius
    return bool(
        br.affected_repos or br.affected_services or br.affected_tests or br.related_adrs
    )


def _has_prior_memory(pack) -> bool:
    if pack is None or _is_v2_pack(pack):
        return False
    return bool(pack.prior_memory)


def _pack_context_sources(pack) -> list[str]:
    if pack is None:
        return []
    if _is_v2_pack(pack):
        sources: list[str] = []
        evidence = pack.current_evidence
        for name in (
            "lexical",
            "symbols",
            "dependency_edges",
            "tests",
            "config",
            "architecture",
        ):
            for item in getattr(evidence, name):
                if item.source and item.source not in sources:
                    sources.append(item.source)
        return sources
    return list(pack.context_sources)


def render_job_context_pack(pack: Any) -> str:
    """Engine-owned renderer. V2 is never pre-rendered on the job."""
    if pack is None:
        return ""
    if _is_v2_pack(pack):
        from agent_control.context.v1_adapter import render_v2

        return render_v2(pack)
    from agent_control.graph.context_pack import render_context_pack_text

    return render_context_pack_text(pack)


def _v1_pack_for_parsers(pack: Any):
    """Structured output premerge is v1-only. V2 has no blast_radius/prior_memory."""
    if pack is None or _is_v2_pack(pack):
        return None
    return pack


load_job_context_pack = _context_pack_from_job
has_graph_blast = _has_graph_blast
has_prior_memory = _has_prior_memory
pack_context_sources = _pack_context_sources


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


def build_official_engine_messages(*, preamble: str, task: str, context_text: str) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) immediately preceding inference."""
    user_prompt = f"Repository context:\n{context_text}\n\nTask: {task}"
    return preamble, user_prompt


def _should_persist_official_engine_messages(job: dict[str, Any]) -> bool:
    if job.get("persist_official_engine_messages") or job.get("eval_memory_consumption_diagnostic"):
        return True
    return os.environ.get("EVAL_MEMORY_CONSUMPTION_DIAGNOSTIC", "").strip() == "1"


def assemble_official_engine_prompts(
    *,
    job: dict[str, Any],
    workspace: Path,
    context_broker: Any | None = None,
    strategy: ExecutionStrategy | None = None,
    persist_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Build the same system/user prompts live inference uses."""
    strategy = strategy or get_execution_strategy()
    kind = job.get("command_intent", {}).get("kind", "inspect")
    risk_class = str(job.get("risk_class", "read_only"))
    pack = _context_pack_from_job(job)

    if kind in REVIEW_KINDS:
        preamble = build_review_system_preamble(
            command_scope=job.get("safety", {}).get("command_scope", kind),
            risk_class=risk_class,
            has_graph_blast=_has_graph_blast(pack),
        )
    elif kind in PLAN_KINDS:
        preamble = build_plan_system_preamble(
            command_scope=job.get("safety", {}).get("command_scope", kind),
            risk_class=risk_class,
            has_graph_blast=_has_graph_blast(pack),
            has_prior_memory=_has_prior_memory(pack),
        )
    elif kind in FIX_KINDS:
        binding = job.get("fix_authorization") or {}
        preamble = build_fix_system_preamble(
            command_scope=job.get("safety", {}).get("command_scope", kind),
            risk_class=risk_class,
            allowed_files=list(binding.get("allowed_files") or []),
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
    if pack is not None:
        pack_text = render_job_context_pack(pack)
        context_text = f"{pack_text}\n\n{context_text}"
        sources = _pack_context_sources(pack) + sources

    system_prompt, user_prompt = build_official_engine_messages(
        preamble=preamble,
        task=task,
        context_text=context_text,
    )
    if persist_dir is not None:
        write_json(
            Path(persist_dir) / "official_engine_messages.json",
            {
                "system": system_prompt,
                "user": user_prompt,
                "context_chars": len(context_text),
            },
        )
    return {
        "system": system_prompt,
        "user": user_prompt,
        "preamble": preamble,
        "context_text": context_text,
        "pack": pack,
        "sources": sources,
    }


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
    if kind in FIX_KINDS:
        if risk_class != "write_patch":
            raise ValueError(
                f"OfficialRLMEngine supports risk_class write_patch for fix, got {risk_class!r}"
            )
        return
    raise ValueError(
        f"OfficialRLMEngine supports read-only inspect/explain/review/plan and fix only, got kind={kind!r}"
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
    system_prompt, user_prompt = build_official_engine_messages(
        preamble=preamble,
        task=task,
        context_text=context_text,
    )
    rlm = RLM(
        backend="openai",
        backend_kwargs=backend_kwargs,
        max_depth=max_depth,
        max_iterations=max_iterations,
        verbose=False,
        custom_system_prompt=system_prompt,
    )
    try:
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


def _response_format_for_kind(kind: str) -> tuple[dict[str, Any] | str | None, str]:
    from agent_shared.models.fix import FixResult
    from agent_shared.models.plan import PlanResult
    from agent_shared.models.review import ReviewResult

    if kind in PLAN_KINDS:
        return PlanResult.model_json_schema(), "schema"
    if kind in REVIEW_KINDS:
        return ReviewResult.model_json_schema(), "schema"
    if kind in FIX_KINDS:
        return FixResult.model_json_schema(), "schema"
    return None, "none"


def _run_single_shot(
    *,
    preamble: str,
    task: str,
    context_text: str,
    endpoint: Any,
    artifact_dir: str | None,
    run_id: str,
    timeout_seconds: float,
    kind: str = "inspect",
) -> tuple[str, dict[str, Any]]:
    system_prompt, user_prompt = build_official_engine_messages(
        preamble=preamble,
        task=task,
        context_text=context_text,
    )
    response_format, format_mode = _response_format_for_kind(kind)
    result: dict[str, Any] | None = None
    used_mode = format_mode
    provider_name = "native_ollama_schema"

    if response_format is not None:
        try:
            from agent_workers.rlm.structured_output_client import StructuredOutputClient

            client = StructuredOutputClient()
            result = client.complete(
                endpoint=endpoint,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_format=response_format,
                timeout_seconds=timeout_seconds,
            )
            used_mode = "schema"
            provider_name = result.get("structured_output_provider", client.provider)
        except Exception:
            try:
                result = chat_completion(
                    endpoint,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=2048,
                    timeout_seconds=timeout_seconds,
                    response_format="json",
                    stream=False,
                )
                used_mode = "json"
                provider_name = "native_ollama_schema"
            except Exception:
                result = None
                used_mode = "none"
                provider_name = "native_ollama_schema"

    if result is None:
        result = chat_completion(
            endpoint,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=2048,
            timeout_seconds=timeout_seconds,
            stream=False,
        )
        used_mode = "none"
        provider_name = "native_ollama_schema"
    elif "structured_output_provider" in result:
        provider_name = str(result.get("structured_output_provider") or provider_name)

    trace = {
        "run_id": run_id,
        "engine": ENGINE_OFFICIAL,
        "mode": "single_shot_openai_compatible",
        "provider": result.get("provider"),
        "structured_output_provider": provider_name,
        "base_url": result.get("base_url"),
        "usage": result.get("usage"),
        "response_chars": len(result.get("content") or ""),
        "timeout_seconds": timeout_seconds,
        "structured_output_format": used_mode,
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

        endpoint = resolve_rlm_gpu_endpoint()
        if not endpoint.base_url:
            raise ValueError("OfficialRLMEngine requires configured MODEL_3080_BASE_URL (rlm role endpoint)")

        persist_dir = None
        if artifact_dir and _should_persist_official_engine_messages(job):
            persist_dir = artifact_dir
        assembled = assemble_official_engine_prompts(
            job=job,
            workspace=workspace,
            context_broker=context_broker,
            strategy=strategy,
            persist_dir=persist_dir,
        )
        preamble = assembled["preamble"]
        context_text = assembled["context_text"]
        pack = assembled["pack"]
        sources = assembled["sources"]
        task = job.get("command_intent", {}).get("natural_language_task", "")
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
        warnings = list(policy.get("warnings") or [])
        use_rlms = _rlms_available()
        if not use_rlms:
            warnings.append("rlms package not installed; used OpenAI-compatible single-shot completion")

        def _call_model(worker_endpoint, suffix: str) -> str:
            cp_endpoint = to_control_plane_endpoint(worker_endpoint)
            task_text = f"{task}{suffix}"
            if use_rlms:
                raw_response, _trace = _run_rlms(
                    preamble=preamble,
                    task=task_text,
                    context_text=context_text,
                    endpoint=cp_endpoint,
                    max_iterations=max_iterations,
                    max_depth=max_depth,
                    artifact_dir=artifact_dir,
                    run_id=job["run_id"],
                )
            else:
                raw_response, _trace = _run_single_shot(
                    preamble=preamble,
                    task=task_text,
                    context_text=context_text,
                    endpoint=cp_endpoint,
                    artifact_dir=artifact_dir,
                    run_id=job["run_id"],
                    timeout_seconds=completion_timeout,
                    kind=kind,
                )
            return raw_response

        review_result = None
        plan_result = None
        fix_result = None
        summary = ""
        if kind in REVIEW_KINDS:
            raw_response = _call_model(resolve_rlm_gpu_endpoint(), "")
            try:
                parsed = parse_review_output(
                    raw_response,
                    context_pack=_v1_pack_for_parsers(pack),
                    run_id=job["run_id"],
                    repair_endpoint=to_control_plane_endpoint(resolve_rlm_gpu_endpoint()),
                    repair_timeout_seconds=min(completion_timeout, 60.0),
                )
            except ReviewParseError as exc:
                if isinstance(exc.__cause__, StructuredParseFailure):
                    failure = exc.__cause__.artifact
                    if artifact_dir:
                        write_json(
                            Path(artifact_dir) / "parse_failure.json",
                            failure.model_dump(mode="json"),
                        )
                raise ValueError(f"Failed to parse review output: {exc}") from exc
            summary, review_result, review_warnings = finalize_review_result(
                parsed,
                known_sources=sources,
                job=job,
                engine=self.name,
                workspace=workspace,
            )
            warnings.extend(review_warnings)
        elif kind in PLAN_KINDS:
            def _parse_plan(raw: str, repair_endpoint) -> tuple[str, Any, list[str]]:
                try:
                    parsed = parse_plan_output(
                        raw,
                        context_pack=_v1_pack_for_parsers(pack),
                        run_id=job["run_id"],
                        repair_endpoint=repair_endpoint,
                        repair_timeout_seconds=min(completion_timeout, 60.0),
                    )
                except PlanParseError as exc:
                    if isinstance(exc.__cause__, StructuredParseFailure):
                        failure = exc.__cause__.artifact
                        if artifact_dir:
                            write_json(
                                Path(artifact_dir) / "parse_failure.json",
                                failure.model_dump(mode="json"),
                            )
                    raise ValueError(f"Failed to parse plan output: {exc}") from exc
                return finalize_plan_result(
                    parsed,
                    known_sources=sources,
                    job=job,
                    engine=self.name,
                    workspace=workspace,
                )

            failed, success = run_quality_gated_attempts(
                kind="plan",
                job=job,
                artifact_dir=artifact_dir,
                engine_name=self.name,
                call_model=_call_model,
                parse_and_finalize=_parse_plan,
            )
            if failed is not None:
                return failed
            assert success is not None and isinstance(success.parsed, PlanResult)
            summary = success.summary or ""
            plan_result = success.parsed
            warnings.extend(success.warnings)
        elif kind in FIX_KINDS:
            binding = job.get("fix_authorization") or {}
            allowed_files = list(binding.get("allowed_files") or [])

            def _parse_fix(raw: str, repair_endpoint) -> tuple[str, Any, list[str]]:
                try:
                    parsed = parse_fix_output(
                        raw,
                        context_pack=_v1_pack_for_parsers(pack),
                        run_id=job["run_id"],
                        repair_endpoint=repair_endpoint,
                        repair_timeout_seconds=min(completion_timeout, 60.0),
                        allowed_files=allowed_files,
                    )
                except FixParseError as exc:
                    if isinstance(exc.__cause__, StructuredParseFailure):
                        failure = exc.__cause__.artifact
                        if artifact_dir:
                            write_json(
                                Path(artifact_dir) / "parse_failure.json",
                                failure.model_dump(mode="json"),
                            )
                    raise ValueError(f"Failed to parse fix output: {exc}") from exc
                return finalize_fix_result(
                    parsed,
                    job=job,
                    engine=self.name,
                )

            failed, success = run_quality_gated_attempts(
                kind="fix",
                job=job,
                artifact_dir=artifact_dir,
                engine_name=self.name,
                call_model=_call_model,
                parse_and_finalize=_parse_fix,
            )
            if failed is not None:
                return failed
            assert success is not None and isinstance(success.parsed, FixResult)
            summary = success.summary or ""
            fix_result = success.parsed
            warnings.extend(success.warnings)
        else:
            raw_response = _call_model(resolve_rlm_gpu_endpoint(), "")
            summary = raw_response
            if not summary:
                summary = f"Read-only {kind} completed for '{task}'; model returned empty content."
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
            fix_result=fix_result,
        )
