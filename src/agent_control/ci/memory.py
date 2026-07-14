"""Verified-only fix memory writeback (Slice 6E.2)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from agent_control.config import Settings, get_settings
from agent_control.events import load_project_events
from agent_control.memory.store import MemoryStore
from agent_shared.constants import FIX_STATUS_CI_VERIFIED
from agent_shared.models.ci import CiVerificationResult, PendingCiRecord
from agent_shared.models.events import AgentRunCompletedEvent
from agent_shared.models.fix import FixResult
from agent_shared.models.memory import (
    MemoryAudit,
    MemoryGovernance,
    MemoryRecord,
    RecommendedNextStep,
)
from agent_shared.repo_identity import normalize_repo_full_name, split_repo_full_name

logger = logging.getLogger(__name__)


def _find_run_completed(
    state_root: Path,
    repository: str,
    fix_run_id: str,
) -> AgentRunCompletedEvent | None:
    for event in load_project_events(state_root, repository):
        if event.get("type") != "agent.run_completed":
            continue
        payload = event.get("payload") or {}
        if payload.get("run_id") != fix_run_id:
            continue
        try:
            return AgentRunCompletedEvent.model_validate(payload)
        except ValueError:
            continue
    return None


def memory_record_from_ci_verified(
    event: AgentRunCompletedEvent,
    *,
    head_commit_sha: str,
) -> MemoryRecord | None:
    """Build fix memory with memory_quality=ci_verified. Idempotent key: fix_run_id+SHA."""
    repo_full_name = normalize_repo_full_name(event.repo_full_name or event.project)
    if repo_full_name is None:
        return None
    owner, repo = split_repo_full_name(repo_full_name)
    now = datetime.now(timezone.utc).isoformat()
    fix: FixResult | None = event.fix_result
    files_touched: list[str] = []
    if fix is not None:
        files_touched = [c.path for c in fix.changes if c.path]

    # Idempotent record id by fix_run_id + SHA
    record_id = f"mem-{event.run_id}-{head_commit_sha[:12]}"
    return MemoryRecord(
        record_id=record_id,
        run_id=event.run_id,
        repo_owner=owner,
        repo_name=repo,
        repo_full_name=repo_full_name,
        issue_id=event.issue_id,
        pr_id=event.opened_pr_number or event.pr_id,
        branch=event.agent_branch or event.branch or "main",
        commit_sha=head_commit_sha,
        source_command="fix",
        source_run_id=event.run_id,
        source_model=event.model_policy,
        source_engine=event.engine,
        source_commit_sha=head_commit_sha,
        confidence="high",
        memory_quality="ci_verified",
        created_at=now,
        updated_at=now,
        files_touched=files_touched,
        governance=MemoryGovernance(
            risk_tags=list(event.risk_tags or []),
            policy_decision="allow",
            risk_class=2,
        ),
        audit=MemoryAudit(
            prompt_hash=event.prompt_hash,
            prompt_hash_source=event.prompt_hash_source,
            summary_hash=event.summary_hash,
            context_sources=list(event.context_sources or []),
            model_tier=event.model_policy,
            engine=event.engine or "",
            ingested_at=now,
        ),
        recommended_next_step=RecommendedNextStep(
            command="human",
            rationale=f"Fix CI verified ({FIX_STATUS_CI_VERIFIED}) for {head_commit_sha[:12]}",
            machine_readable={
                "fix_status": FIX_STATUS_CI_VERIFIED,
                "head_commit_sha": head_commit_sha,
                "opened_pr_number": event.opened_pr_number,
            },
        ),
    )


def writeback_fix_ci_verified(
    state_root: Path,
    *,
    pending: PendingCiRecord,
    result: CiVerificationResult,
    settings: Settings | None = None,
) -> MemoryRecord | None:
    """Memory upsert only when reducer verdict=verified. Idempotent by fix_run_id+SHA."""
    if result.verdict != "verified":
        return None
    settings = settings or get_settings()
    event = _find_run_completed(state_root, pending.repository, pending.fix_run_id)
    if event is None:
        logger.warning(
            "ci_memory_no_run_completed fix_run_id=%s",
            pending.fix_run_id,
        )
        return None

    record = memory_record_from_ci_verified(
        event,
        head_commit_sha=pending.expected_head_commit_sha,
    )
    if record is None:
        return None

    store = MemoryStore(settings.memory_db_path)
    existing = store.get_by_run_id(event.run_id)
    # Prefer exact record_id match for idempotency across SHA
    if existing is not None and existing.record_id == record.record_id:
        if existing.memory_quality == "ci_verified":
            return existing
    return store.upsert_record(record)
