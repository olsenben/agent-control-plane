"""CI observe hook for T08 bounded Qwen loop (no 6F.2 enablement)."""

from __future__ import annotations

import logging
from pathlib import Path

from agent_control.config import Settings
from agent_control.qwen_loop.artifacts import load_qwen_loop_artifact, persist_qwen_loop_artifact
from agent_control.qwen_loop.loop import evaluate_ci_grounded_retry
from agent_control.recursive_context.artifacts import load_recursive_context_artifact
from agent_control.session.storage import load_session_by_run, save_session
from agent_shared.models.ci import FailureEvidenceManifest
from agent_shared.models.qwen_loop import QwenLoopResult

logger = logging.getLogger(__name__)


def _completed_attempts(prior: QwenLoopResult | None) -> int:
    """How many CI-fail cycles have already consumed loop budget."""
    if prior is None:
        return 0
    if prior.ci_verdict != "failing":
        return sum(1 for a in prior.prior_attempts if a.ci_verdict == "failing")
    if prior.action == "retry":
        # Prior retry slot is consumed when the next failing verdict arrives.
        return prior.attempt
    if prior.stop_reason == "budget_exhausted":
        return prior.max_attempts
    # Early stop (insufficient evidence, human_required, …) does not burn the slot.
    return max(0, prior.attempt - 1)


def record_ci_grounded_qwen_loop(
    state_root: Path,
    *,
    repository: str,
    fix_run_id: str,
    ci_verdict: str,
    evidence: FailureEvidenceManifest | None,
    settings: Settings | None = None,
) -> QwenLoopResult | None:
    """Evaluate + persist bounded Qwen loop decision after a CI verdict.

    Does not enqueue repair or expand allowlists (T09). Returns None when no
    session is bound to the fix run.
    """
    del settings  # reserved for future env overrides
    session = load_session_by_run(state_root, repository, fix_run_id)
    if session is None:
        logger.info("qwen_loop_no_session run_id=%s", fix_run_id)
        return None

    prior = load_qwen_loop_artifact(state_root, session.project, session.session_id)
    completed_attempts = _completed_attempts(prior)

    rc = None
    if session.recursive_context is not None:
        rc = load_recursive_context_artifact(state_root, session.project, session.session_id)

    result = evaluate_ci_grounded_retry(
        session_id=session.session_id,
        run_id=fix_run_id,
        repo=session.project,
        ci_verdict=ci_verdict,
        completed_attempts=completed_attempts,
        evidence=evidence,
        recursive_context=rc,
        prior=prior,
    )
    stamped, ref, _created = persist_qwen_loop_artifact(state_root, result)
    session = session.model_copy(update={"qwen_loop": ref, "updated_at": stamped.updated_at})
    save_session(state_root, session)
    logger.info(
        "qwen_loop_recorded session=%s run=%s action=%s attempt=%s/%s stop=%s",
        session.session_id,
        fix_run_id,
        stamped.action,
        stamped.attempt,
        stamped.max_attempts,
        stamped.stop_reason,
    )
    return stamped
