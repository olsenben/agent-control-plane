"""Minimal local RLM engine — Step D placeholder using model router."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_control.model_router import resolve_role_primary
from agent_shared.models.runs import RLMResult
from agent_workers.rlm.constants import ENGINE_MINIMAL
from agent_workers.rlm.fake_engine import FakeRLMEngine
from agent_workers.rlm.prompts import build_system_preamble


class MinimalLocalRLMEngine:
    """Uses configured model endpoint for read-only inspect/explain when available."""

    name = ENGINE_MINIMAL

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
        kind = job.get("command_intent", {}).get("kind", "inspect")
        if kind not in ("inspect", "explain"):
            return FakeRLMEngine().run(
                job,
                workspace,
                policy,
                artifact_dir=artifact_dir,
                context_broker=context_broker,
                tools=tools,
            )

        preamble = build_system_preamble(
            command_scope=job.get("safety", {}).get("command_scope", kind),
            risk_class=str(job.get("risk_class", "read_only")),
        )
        try:
            endpoint = resolve_role_primary("rlm")
            model_note = f"Model endpoint configured: {endpoint.base_url}"
        except ValueError:
            model_note = "Model endpoint not configured; using deterministic fallback text"

        task = job.get("command_intent", {}).get("natural_language_task", "")
        summary = (
            f"{preamble.splitlines()[0]} "
            f"Read-only analysis for '{task}'. {model_note}. "
            "No repo writes, tests, or pushes performed."
        )
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
