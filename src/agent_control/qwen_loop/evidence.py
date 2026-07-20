"""Evidence selection for the bounded recursive Qwen loop."""

from __future__ import annotations

from agent_shared.models.ci import FailureEvidenceManifest
from agent_shared.models.memory_preflight import MemoryPreflight
from agent_shared.models.qwen_loop import QwenLoopBudget, SelectedEvidenceContext
from agent_shared.models.recursive_context import RecursiveContextResult


def select_evidence_context(
    *,
    evidence: FailureEvidenceManifest | None = None,
    recursive_context: RecursiveContextResult | None = None,
    preflight: MemoryPreflight | None = None,
    budget: QwenLoopBudget | None = None,
    extra_refs: list[str] | None = None,
) -> SelectedEvidenceContext:
    """Build a bounded, evidence-selected context packet for the next Qwen pass.

    Preference order (CI-grounded first):
      1. CI failure evidence (6F.1)
      2. recursive_context_result.v1 citations (T07)
      3. deterministic memory preflight citations (5.5 / 8b)
    """
    budget = budget or QwenLoopBudget()
    refs: list[str] = []
    sources: list[str] = []
    fingerprints: list[str] = []
    files: list[str] = []
    rejected: list[str] = []
    failure_class: str | None = None
    rc_digest: str | None = None
    summary_bits: list[str] = []

    def _add_ref(ref: str) -> None:
        if ref and ref not in refs and len(refs) < budget.max_selected_evidence_refs:
            refs.append(ref)

    if evidence is not None:
        sources.append("ci_failure_evidence")
        failure_class = evidence.failure_class
        _add_ref(f"ci_evidence:{evidence.evidence_observation_id}")
        _add_ref(f"ci_run:{evidence.workflow_run_id}")
        if evidence.failure_class:
            fingerprints.append(f"failure_class:{evidence.failure_class}")
            summary_bits.append(f"failure_class={evidence.failure_class}")
        for job in evidence.jobs[:8]:
            _add_ref(f"ci_job:{job.job_id}")
            if job.name:
                fingerprints.append(f"job:{job.name}:{job.conclusion}")
        if evidence.has_terminal_failed_job:
            summary_bits.append("terminal_failed_job")
        if evidence.status != "collected":
            summary_bits.append(f"evidence_status={evidence.status}")

    if recursive_context is not None:
        sources.append("recursive_context")
        rc_digest = recursive_context.artifact_digest or None
        for ref in recursive_context.evidence_refs:
            _add_ref(ref)
        for hyp in recursive_context.rejected_hypotheses:
            if hyp and hyp not in rejected and len(rejected) < budget.max_rejected_hypotheses:
                rejected.append(hyp)
        for hyp in recursive_context.supported_hypotheses:
            if hyp and hyp not in rejected and len(rejected) < budget.max_rejected_hypotheses:
                # supported hypotheses are retained as context, not rejected
                pass
        if recursive_context.stop_reason == "contradictory_evidence":
            summary_bits.append("rc_contradictory_evidence")

    if preflight is not None:
        sources.append("memory_preflight")
        for ref in preflight.citations:
            _add_ref(ref)
        for path in preflight.likely_files:
            if path and path not in files and len(files) < budget.max_likely_files:
                files.append(path)
        for hyp in preflight.rejected_hypotheses_from_prior_runs:
            if hyp and hyp not in rejected and len(rejected) < budget.max_rejected_hypotheses:
                rejected.append(hyp)

    for ref in extra_refs or []:
        _add_ref(ref)

    # Cap summary length.
    summary = "; ".join(summary_bits) if summary_bits else "no_ci_summary"
    if len(summary) > budget.max_selected_chars:
        summary = summary[: budget.max_selected_chars]

    return SelectedEvidenceContext(
        evidence_refs=refs,
        failure_class=failure_class,
        failure_fingerprints=fingerprints[: budget.max_selected_evidence_refs],
        likely_files=files,
        rejected_hypotheses=rejected,
        recursive_context_digest=rc_digest,
        summary=summary,
        selection_sources=sources,
    )


def context_has_usable_evidence(ctx: SelectedEvidenceContext) -> bool:
    """True when retry may proceed under require_evidence_for_retry."""
    if ctx.evidence_refs:
        return True
    if ctx.failure_class and ctx.failure_class != "unknown":
        return True
    return False
