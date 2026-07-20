"""Memory-as-governance: block fix on repeated_failed_fix without new evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_control.config import Settings, get_settings
from agent_control.events import AgentEvent, append_event, deterministic_event_id
from agent_control.memory.store import MemoryStore
from agent_control.project_identity import canonical_project
from agent_shared.models.memory import MemoryRecord
from agent_shared.repo_identity import normalize_repo_full_name

RISK_TAG_REPEATED_FAILED_FIX = "repeated_failed_fix"
EVENT_MEMORY_GOVERNANCE_DENIED = "agent.memory_governance_denied"
DEFAULT_REPEATED_FAILURE_THRESHOLD = 2
REASON_PREFIX = "memory_governance:"


@dataclass
class GovernanceDecision:
    policy_decision: str  # allow | deny
    reason: str | None = None
    failure_class: str | None = None
    attempt_count: int = 0
    threshold: int = DEFAULT_REPEATED_FAILURE_THRESHOLD
    overlapping_files: list[str] = field(default_factory=list)
    risk_tags: list[str] = field(default_factory=list)
    new_evidence: bool = False
    matched_run_ids: list[str] = field(default_factory=list)


def _machine_readable(record: MemoryRecord) -> dict[str, Any]:
    if record.recommended_next_step is None:
        return {}
    mr = record.recommended_next_step.machine_readable or {}
    return dict(mr) if isinstance(mr, dict) else {}


def is_failed_fix_attempt(record: MemoryRecord) -> bool:
    """True when memory records a failed fix / CI failure attempt."""
    if record.source_command != "fix":
        return False
    mr = _machine_readable(record)
    if mr.get("outcome") == "failed" and mr.get("failure_class"):
        return True
    tags = list(record.governance.risk_tags or [])
    return RISK_TAG_REPEATED_FAILED_FIX in tags and bool(mr.get("failure_class"))


def failure_class_of(record: MemoryRecord) -> str | None:
    mr = _machine_readable(record)
    raw = mr.get("failure_class")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def files_of(record: MemoryRecord) -> set[str]:
    files = list(record.files_touched or []) + list(record.files_inspected or [])
    mr = _machine_readable(record)
    extra = mr.get("files") or mr.get("files_touched") or []
    if isinstance(extra, list):
        files.extend(str(p) for p in extra if p)
    return {p for p in files if p}


def paths_overlap(requested: list[str] | None, attempt_files: set[str]) -> bool:
    """Issue-level (empty either side) counts as overlap; else require intersection."""
    req = {p for p in (requested or []) if p}
    if not req or not attempt_files:
        return True
    return bool(req & attempt_files)


def _created_at_key(record: MemoryRecord) -> str:
    return record.created_at or ""


def has_new_evidence(
    records: list[MemoryRecord],
    *,
    after_iso: str,
    failure_class: str,
) -> bool:
    """True when something newer than the last matching failure unlocks another fix."""
    for record in records:
        if _created_at_key(record) <= after_iso:
            continue
        mr = _machine_readable(record)
        if mr.get("new_evidence") is True:
            return True
        if record.source_command in ("review", "plan"):
            if record.evidence_refs or record.findings:
                return True
        # Distinct evidence fingerprint for a later failure of any class counts
        # as new discriminating evidence (operator/CI produced new signal).
        if is_failed_fix_attempt(record):
            prev_fp = None
            for older in records:
                if failure_class_of(older) != failure_class:
                    continue
                if _created_at_key(older) >= _created_at_key(record):
                    continue
                older_mr = _machine_readable(older)
                prev_fp = older_mr.get("evidence_fingerprint")
                break
            cur_fp = mr.get("evidence_fingerprint")
            if cur_fp and prev_fp and cur_fp != prev_fp and failure_class_of(record) != failure_class:
                return True
    return False


def memory_as_governance_check(
    repo_full_name: str,
    issue_id: int,
    *,
    file_paths: list[str] | None = None,
    threshold: int | None = None,
    settings: Settings | None = None,
    store: MemoryStore | None = None,
) -> GovernanceDecision:
    """Deny when memory shows repeated failure class without new evidence."""
    settings = settings or get_settings()
    limit = getattr(settings, "memory_governance_trajectory_limit", 50)
    thresh = (
        threshold
        if threshold is not None
        else int(getattr(settings, "memory_governance_repeated_threshold", DEFAULT_REPEATED_FAILURE_THRESHOLD))
    )
    mem = store or MemoryStore(settings.memory_db_path)
    records = mem.list_for_issue(repo_full_name, issue_id, limit=limit)

    # Group failed attempts by failure_class with file overlap
    by_class: dict[str, list[MemoryRecord]] = {}
    for record in records:
        if not is_failed_fix_attempt(record):
            continue
        cls = failure_class_of(record)
        if not cls:
            continue
        if not paths_overlap(file_paths, files_of(record)):
            continue
        by_class.setdefault(cls, []).append(record)

    for cls, attempts in by_class.items():
        attempts_sorted = sorted(attempts, key=_created_at_key)
        if len(attempts_sorted) < thresh:
            continue
        last = attempts_sorted[-1]
        last_iso = _created_at_key(last)
        if has_new_evidence(records, after_iso=last_iso, failure_class=cls):
            continue
        req_set = set(file_paths or [])
        last_files = files_of(last)
        overlap = sorted((last_files & req_set) if req_set else last_files)
        return GovernanceDecision(
            policy_decision="deny",
            reason=(
                f"{REASON_PREFIX}repeated_failed_fix "
                f"failure_class={cls} attempts={len(attempts_sorted)} "
                f"threshold={thresh} without new evidence"
            ),
            failure_class=cls,
            attempt_count=len(attempts_sorted),
            threshold=thresh,
            overlapping_files=overlap,
            risk_tags=[RISK_TAG_REPEATED_FAILED_FIX],
            new_evidence=False,
            matched_run_ids=[a.run_id for a in attempts_sorted],
        )

    return GovernanceDecision(policy_decision="allow", threshold=thresh)


def append_memory_governance_denied(
    state_root: Path,
    *,
    project: str,
    issue_id: int,
    approval_target_id: str,
    decision: GovernanceDecision,
    comment_id: str | int | None = None,
) -> tuple[Path, bool]:
    """Idempotent audit event for a memory-governance deny."""
    repo = canonical_project(project)
    cid = str(comment_id or "none")
    delivery = (
        f"{cid}:memory_governance:{repo}:{issue_id}:"
        f"{approval_target_id}:{decision.failure_class}:{decision.attempt_count}"
    )
    event_type = EVENT_MEMORY_GOVERNANCE_DENIED
    event_id = deterministic_event_id("ct103", delivery, event_type)
    payload = {
        "schema_version": "memory_governance_denied.v1",
        "type": event_type,
        "project": repo,
        "issue_id": issue_id,
        "approval_target_id": approval_target_id,
        "policy_decision": "deny",
        "reason": decision.reason,
        "failure_class": decision.failure_class,
        "attempt_count": decision.attempt_count,
        "threshold": decision.threshold,
        "overlapping_files": list(decision.overlapping_files),
        "matched_run_ids": list(decision.matched_run_ids),
        "risk_tags": list(decision.risk_tags or [RISK_TAG_REPEATED_FAILED_FIX]),
        "risk_class": 2,
        "denied_at": datetime.now(timezone.utc).isoformat(),
    }
    event = AgentEvent(
        event_id=event_id,
        type=event_type,
        raw_event_type=event_type,
        source="ct103",
        delivery_id=delivery,
        project=repo,
        payload=payload,
        recorded_at=datetime.now(timezone.utc).isoformat(),
    )
    return append_event(state_root, event)


def check_for_fix_request(
    *,
    project: str,
    issue_id: int,
    file_paths: list[str] | None,
    settings: Settings | None = None,
) -> GovernanceDecision:
    """Convenience wrapper using canonical project → repo full name."""
    repo = normalize_repo_full_name(project) or canonical_project(project)
    return memory_as_governance_check(
        repo,
        issue_id,
        file_paths=file_paths,
        settings=settings,
    )
