"""Deterministic RLM engine for inspect MVP — no model API calls."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_shared.models.review import ReviewFinding, ReviewResult, stub_blast_radius
from agent_shared.models.runs import RLMResult
from agent_workers.rlm.constants import ENGINE_FAKE
from agent_workers.rlm.official_engine import gather_read_only_context
from agent_workers.rlm.review_finalize import finalize_review_result
from agent_workers.rlm.trace import append_trace_event


def _build_fake_review_result(
    job: dict[str, Any],
    workspace: Path,
    context_broker: Any | None,
) -> tuple[ReviewResult, list[str]]:
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

    files_inspected = sources[:2] if sources else []
    finding_file = files_inspected[0] if files_inspected else None
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
        blast_radius=stub_blast_radius(),
        confidence="medium",
        recommended_next_command="/agent plan",
        risk_tags=[],
    )
    return review, sources


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
