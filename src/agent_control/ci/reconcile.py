"""Startup / periodic CI reconciler (Slice 6E.1)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_control.ci.aggregate import normalize_conclusion, result_from_pending
from agent_control.ci.artifacts import load_verification_current, write_verification_current
from agent_control.ci.observe import apply_observation, fix_ci_observe_enabled
from agent_control.ci.pending import list_pending_ci, load_pending_ci, save_pending_ci
from agent_control.config import Settings, get_settings
from agent_control.gitea_client import GiteaClient
from agent_shared.models.ci import WorkflowObservation
from agent_shared.repo_identity import split_repo_full_name

logger = logging.getLogger(__name__)


def reconcile_pending_ci(
    state_root: Path,
    *,
    project: str | None = None,
    settings: Settings | None = None,
    gitea_client: GiteaClient | None = None,
) -> list[dict[str, Any]]:
    """Poll Actions API for pending records (catch dropped/duplicate webhooks)."""
    settings = settings or get_settings()
    if not fix_ci_observe_enabled(settings):
        return [{"skipped": True, "reason": "fix_ci_observe_disabled"}]

    client = gitea_client or GiteaClient(settings)
    results: list[dict[str, Any]] = []
    pending_list = list_pending_ci(state_root, project, include_terminal=False)

    for pending in pending_list:
        if pending.current_verdict in ("verified", "superseded", "expired"):
            continue
        owner, repo = split_repo_full_name(pending.repository)
        try:
            runs = client.list_workflow_runs(
                owner,
                repo,
                head_sha=pending.expected_head_commit_sha,
                status=None,
                limit=50,
            )
        except Exception as exc:
            logger.warning(
                "ci_reconcile_list_failed fix_run_id=%s err=%s",
                pending.fix_run_id,
                exc,
            )
            results.append(
                {
                    "fix_run_id": pending.fix_run_id,
                    "ok": False,
                    "error": str(exc),
                }
            )
            continue

        applied = 0
        for run in runs:
            status = str(run.get("status") or "")
            conclusion = run.get("conclusion")
            if status not in ("completed", "success", "failure") and not conclusion:
                continue
            obs = WorkflowObservation(
                workflow_id=str(run.get("workflow_id") or "") or None,
                path=str(run.get("path") or run.get("workflow_path") or ""),
                display_name=str(run.get("name") or run.get("display_title") or ""),
                workflow_run_id=str(run.get("id") or ""),
                run_attempt=int(run.get("run_attempt") or run.get("attempt") or 1),
                status=status,
                conclusion=normalize_conclusion(conclusion, status=status),
                head_sha=str(
                    run.get("head_sha")
                    or (run.get("head_commit") or {}).get("id")
                    or pending.expected_head_commit_sha
                ),
                pr_number=pending.opened_pr_number,
                delivery_id=f"reconcile:{run.get('id')}:{run.get('run_attempt') or 1}",
                observed_at=datetime.now(timezone.utc).isoformat(),
                api_verification_status="confirmed",
            )
            if not obs.workflow_run_id:
                continue
            outcome = apply_observation(
                state_root,
                repository=pending.repository,
                head_sha=pending.expected_head_commit_sha,
                observation=obs,
                settings=settings,
                post_comment=True,
            )
            if outcome is not None:
                applied += 1

        refreshed = load_pending_ci(state_root, pending.repository, pending.fix_run_id)
        results.append(
            {
                "fix_run_id": pending.fix_run_id,
                "ok": True,
                "applied_observations": applied,
                "verdict": refreshed.current_verdict if refreshed else pending.current_verdict,
            }
        )
    return results


def refresh_artifact_snapshot(
    state_root: Path,
    project: str,
    fix_run_id: str,
) -> Path | None:
    """Ensure verification-current.json exists from pending + ledger rebuild."""
    from agent_control.ci.observe import rebuild_result_from_ledger

    pending = load_pending_ci(state_root, project, fix_run_id)
    if pending is None or not pending.artifact_root:
        return None
    artifact_root = Path(pending.artifact_root)
    result = rebuild_result_from_ledger(state_root, project, fix_run_id)
    if result is None:
        result = result_from_pending(pending)
    existing = load_verification_current(artifact_root)
    if existing is not None and existing.verdict_revision >= result.verdict_revision:
        return artifact_root / "ci" / "verification-current.json"
    path = write_verification_current(artifact_root, result)
    pending.current_verdict = result.verdict
    pending.verdict_revision = result.verdict_revision
    save_pending_ci(state_root, pending)
    return path
