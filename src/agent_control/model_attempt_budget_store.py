"""Durable CT103 model attempt budget (V6 T04 / QA F-07)."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from agent_shared.models.model_attempt_budget import (
    AttemptBudgetTracker,
    BudgetKind,
    ModelAttemptBudget,
    budget_from_env,
)

logger = logging.getLogger(__name__)


def _budget_path(state_root: Path, project: str, budget_key: str) -> Path:
    owner, repo = project.split("/", 1)
    return state_root / "projects" / owner / repo / "budgets" / f"{budget_key}.json"


def load_durable_budget(
    state_root: Path,
    *,
    project: str,
    budget_key: str,
    limits: ModelAttemptBudget | None = None,
) -> AttemptBudgetTracker:
    path = _budget_path(state_root, project, budget_key)
    tracker = AttemptBudgetTracker(limits=limits or budget_from_env().limits)
    if not path.is_file():
        return tracker
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return tracker
    lim = data.get("limits") or {}
    if lim and limits is None:
        tracker.limits = ModelAttemptBudget(
            max_infrastructure_attempts=int(
                lim.get("max_infrastructure_attempts", tracker.limits.max_infrastructure_attempts)
            ),
            max_provider_routes=int(lim.get("max_provider_routes", tracker.limits.max_provider_routes)),
            max_schema_repair_attempts=int(
                lim.get("max_schema_repair_attempts", tracker.limits.max_schema_repair_attempts)
            ),
            max_quality_retries=int(lim.get("max_quality_retries", tracker.limits.max_quality_retries)),
            max_total_completion_attempts=int(
                lim.get("max_total_completion_attempts", tracker.limits.max_total_completion_attempts)
            ),
        )
    tracker.infrastructure_attempts = int(data.get("infrastructure_attempts") or 0)
    tracker.provider_routes = int(data.get("provider_routes") or 0)
    tracker.schema_repair_attempts = int(data.get("schema_repair_attempts") or 0)
    tracker.quality_retries = int(data.get("quality_retries") or 0)
    tracker.total_completion_attempts = int(data.get("total_completion_attempts") or 0)
    return tracker


def save_durable_budget(
    state_root: Path,
    *,
    project: str,
    budget_key: str,
    tracker: AttemptBudgetTracker,
) -> Path:
    path = _budget_path(state_root, project, budget_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = tracker.as_dict()
    body["limits"] = tracker.limits.model_dump(mode="json")
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(body, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return path


def reserve_attempt(
    state_root: Path,
    *,
    project: str,
    budget_key: str,
    kind: BudgetKind,
    idempotency_key: str | None = None,
) -> tuple[bool, AttemptBudgetTracker]:
    """Atomically reserve one attempt. Duplicate idempotency_key does not double-charge."""
    path = _budget_path(state_root, project, budget_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix(".lock")
    for _ in range(50):
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            break
        except FileExistsError:
            continue
    try:
        tracker = load_durable_budget(state_root, project=project, budget_key=budget_key)
        reserved = set()
        meta_path = path.with_suffix(".keys.json")
        if meta_path.is_file():
            try:
                reserved = set(json.loads(meta_path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                reserved = set()
        if idempotency_key and idempotency_key in reserved:
            return True, tracker
        ok = tracker.consume(kind)
        if not ok:
            save_durable_budget(state_root, project=project, budget_key=budget_key, tracker=tracker)
            return False, tracker
        if idempotency_key:
            reserved.add(idempotency_key)
            meta_path.write_text(json.dumps(sorted(reserved)), encoding="utf-8")
        save_durable_budget(state_root, project=project, budget_key=budget_key, tracker=tracker)
        return True, tracker
    finally:
        try:
            lock.unlink(missing_ok=True)
        except OSError:
            pass


def emit_budget_exhausted(
    state_root: Path,
    *,
    project: str,
    run_id: str | None = None,
    session_id: str | None = None,
    tracker: AttemptBudgetTracker | None = None,
) -> None:
    """Durable control_decision when shared attempt budget is exhausted."""
    from agent_control.observe.events import append_control_decision

    append_control_decision(
        state_root,
        project=project,
        kind="budget_exhausted",
        summary="model attempt budget exhausted",
        session_id=session_id,
        run_id=run_id,
        metadata=tracker.as_dict() if tracker else {},
    )
