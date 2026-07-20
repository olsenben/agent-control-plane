"""Memory retrieval for context-pack compilation."""

from __future__ import annotations

from agent_control.config import Settings, get_settings
from agent_control.memory.store import MemoryStore
from agent_shared.models.memory import MemoryRecord
from agent_shared.repo_identity import normalize_repo_full_name

STALENESS_REASON_SHA_MISMATCH = "memory_source_commit_differs_from_current_target"

PRIOR_MEMORY_HEADER = (
    "These are prior model-generated findings from earlier runs.\n"
    "Treat them as hypotheses unless marked human_verified or ci_verified.\n"
    "Prefer consistency, but do not assume they are correct."
)


def apply_staleness(
    record: MemoryRecord,
    *,
    current_target_sha: str | None,
) -> MemoryRecord:
    if not current_target_sha or not record.source_commit_sha:
        return record
    if record.source_commit_sha == current_target_sha:
        return record
    return record.model_copy(
        update={
            "is_stale": True,
            "staleness_reason": STALENESS_REASON_SHA_MISMATCH,
            "staleness": "stale",
        }
    )


def record_to_prior_memory_dict(record: MemoryRecord) -> dict:
    """Distilled capsule for context_pack.prior_memory (no nested blobs)."""
    recommended = None
    if record.recommended_next_step:
        recommended = {
            "command": record.recommended_next_step.command,
            "rationale": record.recommended_next_step.rationale,
        }
    return {
        "record_id": record.record_id,
        "run_id": record.run_id,
        "session_id": record.session_id,
        "source_command": record.source_command,
        "source_run_id": record.source_run_id,
        "source_engine": record.source_engine,
        "confidence": record.confidence,
        "memory_quality": record.memory_quality,
        "epistemic_status": record.epistemic_status,
        "evidence_refs": list(record.evidence_refs),
        "is_stale": record.is_stale,
        "staleness_reason": record.staleness_reason,
        "created_at": record.created_at,
        "files_inspected": record.files_inspected,
        "findings": [f.model_dump(mode="json") for f in record.findings],
        "blast_radius": record.blast_radius.model_dump(mode="json"),
        "unresolved_questions": record.unresolved_questions,
        "uncertain_hypotheses": record.uncertain_hypotheses,
        "recommended_next_step": recommended,
    }


def _order_records_for_plan(records: list[MemoryRecord]) -> list[MemoryRecord]:
    """Plan dispatch: latest review first, then latest plan, then remaining trajectory."""
    reviews = [r for r in records if r.source_command == "review"]
    plans = [r for r in records if r.source_command == "plan"]
    ordered: list[MemoryRecord] = []
    if reviews:
        ordered.append(reviews[0])
    if plans:
        latest_plan = plans[0]
        if not ordered or ordered[0].run_id != latest_plan.run_id:
            ordered.append(latest_plan)
    seen = {r.run_id for r in ordered}
    for record in records:
        if record.run_id not in seen:
            ordered.append(record)
            seen.add(record.run_id)
    return ordered


def _fit_capsules_to_budget(capsules: list[dict], max_chars: int) -> list[dict]:
    import json

    from agent_workers.rlm.budget import truncate_text

    kept: list[dict] = []
    for capsule in capsules:
        trial = kept + [capsule]
        if len(json.dumps(trial, indent=2)) <= max_chars:
            kept = trial
        else:
            break
    if kept:
        return kept
    if not capsules:
        return []
    blob = json.dumps([capsules[0]], indent=2)
    if len(blob) <= max_chars:
        return [capsules[0]]
    truncated = truncate_text(blob, max_chars)
    try:
        parsed = json.loads(truncated)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass
    return [capsules[0]]


def get_memory_trajectory(
    repo_full_name: str,
    issue_id: int,
    *,
    current_target_sha: str | None = None,
    limit: int = 5,
    settings: Settings | None = None,
) -> list[MemoryRecord]:
    settings = settings or get_settings()
    store = MemoryStore(settings.memory_db_path)
    records = store.list_for_issue(repo_full_name, issue_id, limit=limit)
    return [
        apply_staleness(record, current_target_sha=current_target_sha) for record in records
    ]


def retrieve_prior_memory_dicts(
    project: str,
    issue_id: int,
    *,
    current_target_sha: str | None = None,
    command_kind: str | None = None,
    limit: int = 5,
    max_chars: int = 3000,
    settings: Settings | None = None,
) -> list[dict]:
    repo_full_name = normalize_repo_full_name(project)
    if repo_full_name is None:
        return []
    records = get_memory_trajectory(
        repo_full_name,
        issue_id,
        current_target_sha=current_target_sha,
        limit=limit,
        settings=settings,
    )
    if not records:
        return []

    if command_kind == "plan":
        records = _order_records_for_plan(records)

    capsules = [record_to_prior_memory_dict(r) for r in records]
    return _fit_capsules_to_budget(capsules, max_chars)
