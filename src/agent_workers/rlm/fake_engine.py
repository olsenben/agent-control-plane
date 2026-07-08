"""Deterministic RLM engine for inspect MVP — no model API calls."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_shared.models.fix import FixFileChange, FixResult
from agent_shared.models.plan import PlanResult, PlanStep
from agent_shared.models.review import ReviewFinding, ReviewResult, stub_blast_radius
from agent_shared.models.runs import RLMResult
from agent_workers.rlm.constants import ENGINE_FAKE
from agent_workers.rlm.official_engine import gather_read_only_context
from agent_workers.rlm.task_scope import pick_plan_step_files
from agent_workers.rlm.plan_finalize import finalize_plan_result
from agent_workers.rlm.fix_finalize import finalize_fix_result
from agent_workers.rlm.review_finalize import finalize_review_result
from agent_workers.rlm.trace import append_trace_event


def _has_graph_blast_from_pack(pack) -> bool:
    br = pack.blast_radius
    return bool(
        br.affected_repos or br.affected_services or br.affected_tests or br.related_adrs
    )


def _build_fake_review_result(
    job: dict[str, Any],
    workspace: Path,
    context_broker: Any | None,
) -> tuple[ReviewResult, list[str]]:
    from agent_shared.models.context_pack import ContextPack

    task = job.get("command_intent", {}).get("natural_language_task", "")
    sources: list[str] = []
    if context_broker is not None:
        _, sources = gather_read_only_context(context_broker, max_files=3, max_chars=8000)
    elif workspace.exists():
        for path in sorted(workspace.iterdir()):
            if path.is_file() and not path.name.startswith("."):
                sources.append(path.name)
                if len(sources) >= 3:
                    break

    pack_raw = job.get("context_pack")
    pack = None
    if pack_raw:
        pack = pack_raw if isinstance(pack_raw, ContextPack) else ContextPack.model_validate(pack_raw)
        sources = list(pack.context_sources) + sources

    files_inspected = sources[:2] if sources else []
    finding_file = files_inspected[0] if files_inspected else None
    blast = stub_blast_radius()
    if pack is not None and _has_graph_blast_from_pack(pack):
        blast = pack.blast_radius

    review = ReviewResult(
        findings=[
            ReviewFinding(
                id="F-001",
                severity="info",
                summary=(
                    f"Fake review for {job['project']}: analyzed task '{task or 'review'}'. "
                    "No model API calls were made."
                ),
                file=finding_file,
                confidence=0.7,
                risk_tags=[],
            )
        ],
        files_inspected=files_inspected,
        blast_radius=blast,
        confidence="medium",
        recommended_next_command="/agent plan",
        risk_tags=[],
    )
    return review, sources


def _build_fake_plan_result(
    job: dict[str, Any],
    workspace: Path,
    context_broker: Any | None,
) -> tuple[PlanResult, list[str]]:
    from agent_shared.models.context_pack import ContextPack

    task = job.get("command_intent", {}).get("natural_language_task", "")
    sources: list[str] = []
    if context_broker is not None:
        _, sources = gather_read_only_context(context_broker, max_files=3, max_chars=8000)
    elif workspace.exists():
        for path in sorted(workspace.iterdir()):
            if path.is_file() and not path.name.startswith("."):
                sources.append(path.name)
                if len(sources) >= 3:
                    break

    pack_raw = job.get("context_pack")
    pack = None
    if pack_raw:
        pack = pack_raw if isinstance(pack_raw, ContextPack) else ContextPack.model_validate(pack_raw)
        sources = list(pack.context_sources) + sources

    blast = stub_blast_radius()
    ci_hints: list[str] = []
    prior_note = ""
    if pack is not None and pack.prior_memory:
        first = pack.prior_memory[0]
        prior_run = first.get("run_id") or first.get("source_run_id") or "prior-run"
        prior_note = f" Prior review run {prior_run}."
        findings = first.get("findings") or []
        if findings:
            prior_note += f" Finding {findings[0].get('id', 'F-001')}: {findings[0].get('summary', '')[:80]}."

    if pack is not None and _has_graph_blast_from_pack(pack):
        blast = pack.blast_radius
        ci_hints = list(blast.affected_tests[:3])

    step_files = pick_plan_step_files(task, sources)

    plan = PlanResult(
        scope_summary=f"Fake plan for {job['project']}: {task or 'plan from prior review context'}.{prior_note}",
        steps=[
            PlanStep(
                id="S-001",
                summary="Implement scoped changes with tests",
                files=step_files,
            )
        ],
        ci_hints=ci_hints or ["pytest -q"],
        blast_radius=blast,
        assumptions=["FakeRLMEngine — no model API calls"],
        confidence="medium",
        recommended_next_command="/agent fix",
        risk_tags=[],
    )
    return plan, sources


def _build_fake_fix_result(
    job: dict[str, Any],
    workspace: Path,
) -> FixResult:
    binding = job.get("fix_authorization") or {}
    allowed = list(binding.get("allowed_files") or [])
    target_path = allowed[0] if allowed else "README.md"
    target = workspace / target_path
    if target.is_file():
        content = target.read_text(encoding="utf-8") + "\n# fake fix applied\n"
        edit_kind: str = "replace"
    else:
        content = "# fake fix created\n"
        edit_kind = "create"

    return FixResult(
        scope_summary=binding.get("plan_summary") or f"Fake fix for {job['project']}",
        files_changed=[target_path],
        changes=[
            FixFileChange(
                path=target_path,
                summary="FakeRLMEngine local patch",
                edit_kind=edit_kind,  # type: ignore[arg-type]
                content=content,
            )
        ],
        ci_hints=list(binding.get("ci_hints") or ["pytest -q"]),
        risk_tags=[],
        confidence="medium",
        approval_target_id=str(binding.get("approval_target_id") or ""),
        plan_run_id=str(binding.get("plan_run_id") or ""),
    )


class FakeRLMEngine:
    name = ENGINE_FAKE

    def run(
        self,
        job: dict[str, Any],
        workspace: Path,
        policy: dict[str, Any],
        *,
        artifact_dir: str | None = None,
        context_broker: Any | None = None,
        tools: Any | None = None,
    ) -> RLMResult:
        del tools
        kind = job.get("command_intent", {}).get("kind", "inspect")
        task = job.get("command_intent", {}).get("natural_language_task", "")
        warnings = list(policy.get("warnings") or [])

        if kind == "review":
            review, sources = _build_fake_review_result(job, workspace, context_broker)
            append_trace_event(
                artifact_dir,
                {
                    "run_id": job["run_id"],
                    "engine": self.name,
                    "event": "context_gathered",
                    "sources": sources,
                },
            )
            summary, review_result, review_warnings = finalize_review_result(
                review,
                known_sources=sources,
                job=job,
                engine=self.name,
            )
            warnings.extend(review_warnings)
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
            )

        if kind == "plan":
            plan, sources = _build_fake_plan_result(job, workspace, context_broker)
            append_trace_event(
                artifact_dir,
                {
                    "run_id": job["run_id"],
                    "engine": self.name,
                    "event": "context_gathered",
                    "sources": sources,
                },
            )
            summary, plan_result, plan_warnings = finalize_plan_result(
                plan,
                known_sources=sources,
                job=job,
                engine=self.name,
            )
            warnings.extend(plan_warnings)
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
                plan_result=plan_result,
            )

        if kind == "fix":
            fix = _build_fake_fix_result(job, workspace)
            append_trace_event(
                artifact_dir,
                {
                    "run_id": job["run_id"],
                    "engine": self.name,
                    "event": "context_gathered",
                    "sources": list(binding.get("allowed_files") or []) if (binding := job.get("fix_authorization")) else [],
                },
            )
            summary, fix_result, fix_warnings = finalize_fix_result(
                fix,
                job=job,
                engine=self.name,
            )
            warnings.extend(fix_warnings)
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
                fix_result=fix_result,
            )

        summary = (
            f"Inspect summary for {job['project']}: analyzed task '{task}'. "
            f"Workspace at {workspace}. FakeRLMEngine made no model API calls."
        )
        if policy.get("warnings"):
            summary += f" Warnings: {'; '.join(policy['warnings'])}"
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
        )
