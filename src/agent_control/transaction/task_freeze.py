"""Freeze Gitea issue content at transaction creation. No LLM. Read-only get_issue."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_control.transaction.evidence.task_receipt import (
    FrozenTaskIssue,
    fetch_gitea_issue,
    freeze_gitea_issue,
)

TASK_FREEZE_FILENAME = "task_issue_freeze.json"
TASK_DIGEST = "TASK_DIGEST"
REQUIRED_TASK_EVIDENCE_UNAVAILABLE = "REQUIRED_EVIDENCE_UNAVAILABLE"


class TaskFreezeError(RuntimeError):
    """Fail-closed task freeze (get_issue failed or issue id unbound)."""

    def __init__(self, reason: str, message: str = "") -> None:
        self.reason = reason
        super().__init__(message or reason)


@dataclass(frozen=True)
class TaskFreezeResult:
    freeze: FrozenTaskIssue | None
    issue_id: int | None
    digest: str | None
    attempted: bool
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.freeze is not None and not self.error


def issue_id_from_provider_task(provider_task_id: str | None) -> int | None:
    text = str(provider_task_id or "").strip()
    if not text or not text.isdigit():
        return None
    value = int(text)
    return value if value >= 1 else None


def freeze_to_payload(freeze: FrozenTaskIssue) -> dict[str, Any]:
    return {
        "repository": freeze.repository,
        "issue_id": freeze.issue_id,
        "content": freeze.content,
        "digest": freeze.digest,
        TASK_DIGEST: freeze.digest,
        "body": freeze.body,
        "labels": list(freeze.labels),
        "structured": dict(freeze.structured),
        "missing_structured_block": freeze.missing_structured_block,
        "llm_parsed": False,
    }


def freeze_from_payload(payload: dict[str, Any]) -> FrozenTaskIssue:
    labels = payload.get("labels") or []
    return FrozenTaskIssue(
        repository=str(payload.get("repository") or ""),
        issue_id=int(payload.get("issue_id") or 0),
        content=str(payload.get("content") or ""),
        digest=str(payload.get("digest") or payload.get(TASK_DIGEST) or ""),
        body=str(payload.get("body") or ""),
        labels=tuple(str(item) for item in labels),
        structured=dict(payload.get("structured") or {}),
        missing_structured_block=bool(payload.get("missing_structured_block")),
    )


def persist_task_freeze(path: Path, result: TaskFreezeResult) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        TASK_DIGEST: result.digest,
        "issue_id": result.issue_id,
        "attempted": result.attempted,
        "error": result.error,
        "llm_parsed": False,
    }
    if result.freeze is not None:
        payload["freeze"] = freeze_to_payload(result.freeze)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)
    return path


def load_task_freeze(path: Path) -> TaskFreezeResult | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    freeze = None
    raw = payload.get("freeze")
    if isinstance(raw, dict):
        freeze = freeze_from_payload(raw)
    return TaskFreezeResult(
        freeze=freeze,
        issue_id=int(payload["issue_id"]) if payload.get("issue_id") is not None else None,
        digest=str(payload.get(TASK_DIGEST) or (freeze.digest if freeze is not None else "") or "")
        or None,
        attempted=bool(payload.get("attempted", True)),
        error=str(payload["error"]) if payload.get("error") else None,
    )


def _default_issue_client() -> Any:
    from agent_control.gitea_client import GiteaClient

    return GiteaClient()


def freeze_task_issue_at_creation(
    *,
    repository: str,
    provider_task_id: str | None,
    store_path: Path,
    client: Any | None = None,
    reuse_existing: bool = True,
) -> TaskFreezeResult:
    """Read-only get_issue then FrozenTaskIssue / TASK_DIGEST. Later edits do not mutate."""
    if reuse_existing:
        existing = load_task_freeze(store_path)
        if existing is not None and existing.attempted:
            return existing
    issue_id = issue_id_from_provider_task(provider_task_id)
    if issue_id is None:
        result = TaskFreezeResult(
            freeze=None,
            issue_id=None,
            digest=None,
            attempted=True,
            error=REQUIRED_TASK_EVIDENCE_UNAVAILABLE,
        )
        persist_task_freeze(store_path, result)
        return result
    issue_client = client if client is not None else _default_issue_client()
    try:
        payload = fetch_gitea_issue(issue_client, repository, issue_id)
    except Exception:
        result = TaskFreezeResult(
            freeze=None,
            issue_id=issue_id,
            digest=None,
            attempted=True,
            error=REQUIRED_TASK_EVIDENCE_UNAVAILABLE,
        )
        persist_task_freeze(store_path, result)
        return result
    if not payload:
        result = TaskFreezeResult(
            freeze=None,
            issue_id=issue_id,
            digest=None,
            attempted=True,
            error=REQUIRED_TASK_EVIDENCE_UNAVAILABLE,
        )
        persist_task_freeze(store_path, result)
        return result
    freeze = freeze_gitea_issue(payload, repository=repository)
    result = TaskFreezeResult(
        freeze=freeze,
        issue_id=issue_id,
        digest=freeze.digest,
        attempted=True,
    )
    persist_task_freeze(store_path, result)
    return result


def p4_live_kwargs(result: TaskFreezeResult, *, repository: str, task_id: str | None = None) -> dict[str, Any]:
    """P4 adapter kwargs. Never includes a Gitea client or write token."""
    if not result.ok or result.freeze is None:
        return {"unavailable_reason": result.error or REQUIRED_TASK_EVIDENCE_UNAVAILABLE}
    return {
        "frozen_issue": result.freeze,
        "expected_issue_id": result.issue_id,
        "expected_repository": repository,
        "task_id": task_id,
    }
