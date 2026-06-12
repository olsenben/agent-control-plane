"""Deterministic RLM engine for inspect MVP — no model API calls."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_shared.models.runs import RLMResult
from agent_workers.rlm.constants import ENGINE_FAKE


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
        task = job.get("command_intent", {}).get("natural_language_task", "")
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
            warnings=list(policy.get("warnings") or []),
        )
