"""Authoritative publish_state machine + publish intent (CT103)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from agent_shared.models.publish import BrokerPublishState, PublishIntent, PublishRecord

_TERMINAL = frozenset({"succeeded", "rejected", "failed_terminal"})
_CAS_FROM: dict[BrokerPublishState, frozenset[BrokerPublishState]] = {
    "not_requested": frozenset({"queued"}),
    "queued": frozenset({"validating", "failed_retryable", "failed_terminal"}),
    "validating": frozenset({"rejected", "remote_pending", "failed_retryable", "failed_terminal"}),
    "remote_pending": frozenset({"succeeded", "failed_retryable", "failed_terminal"}),
    "failed_retryable": frozenset({"queued", "validating", "failed_terminal"}),
    "rejected": frozenset(),
    "succeeded": frozenset(),
    "failed_terminal": frozenset(),
}


def publish_job_id(*, run_id: str, kind: str, attempt_id: str, bundle_id: str) -> str:
    return f"publish-{run_id}-{kind}-{attempt_id}-{bundle_id}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def publish_record_path(state_root: Path, run_id: str, bundle_id: str) -> Path:
    return state_root / "publish-results" / run_id / bundle_id / "publish_record.json"


def intent_path(state_root: Path, project: str, expected_commit_sha: str) -> Path:
    safe_proj = project.replace("/", "__")
    return (
        state_root
        / "publish-intents"
        / safe_proj
        / f"{expected_commit_sha}.json"
    )


def load_publish_record(state_root: Path, run_id: str, bundle_id: str) -> PublishRecord | None:
    path = publish_record_path(state_root, run_id, bundle_id)
    if not path.is_file():
        return None
    try:
        return PublishRecord.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValueError):
        return None


def save_publish_record(state_root: Path, record: PublishRecord) -> Path:
    path = publish_record_path(state_root, record.run_id, record.bundle_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = record.model_dump_json(indent=2)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, path)
    return path


def cas_transition(
    state_root: Path,
    *,
    run_id: str,
    kind: str,
    attempt_id: str,
    bundle_id: str,
    from_state: BrokerPublishState,
    to_state: BrokerPublishState,
    **updates: object,
) -> PublishRecord | None:
    """Compare-and-set publish_state. Returns updated record or None if CAS failed."""
    allowed = _CAS_FROM.get(from_state, frozenset())
    if to_state not in allowed and from_state != to_state:
        return None

    existing = load_publish_record(state_root, run_id, bundle_id)
    if existing is None:
        if from_state != "not_requested":
            return None
        existing = PublishRecord(
            run_id=run_id,
            kind=kind,
            attempt_id=attempt_id,
            bundle_id=bundle_id,
            publish_state="not_requested",
            job_id=publish_job_id(
                run_id=run_id, kind=kind, attempt_id=attempt_id, bundle_id=bundle_id
            ),
        )
    if existing.publish_state != from_state:
        return None

    patch = dict(updates)
    patch["publish_state"] = to_state
    patch["updated_at"] = _now()
    updated = existing.model_copy(update=patch)
    save_publish_record(state_root, updated)
    return updated


def try_enqueue_cas(
    state_root: Path,
    *,
    run_id: str,
    kind: str,
    attempt_id: str,
    bundle_id: str,
    project: str | None = None,
    approval_id: str | None = None,
    approval_target_id: str | None = None,
) -> PublishRecord | None:
    """Atomic not_requested → queued. None if already queued/terminal."""
    existing = load_publish_record(state_root, run_id, bundle_id)
    if existing is not None and existing.publish_state != "not_requested":
        return None
    return cas_transition(
        state_root,
        run_id=run_id,
        kind=kind,
        attempt_id=attempt_id,
        bundle_id=bundle_id,
        from_state="not_requested",
        to_state="queued",
        project=project,
        approval_id=approval_id,
        approval_target_id=approval_target_id,
    )


def save_publish_intent(state_root: Path, intent: PublishIntent) -> Path:
    path = intent_path(state_root, intent.project, intent.expected_commit_sha)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(intent.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return path


def load_publish_intent(
    state_root: Path,
    project: str,
    expected_commit_sha: str,
) -> PublishIntent | None:
    path = intent_path(state_root, project, expected_commit_sha)
    if not path.is_file():
        return None
    try:
        return PublishIntent.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValueError):
        return None


def find_intent_by_repo_sha(
    state_root: Path,
    repository: str,
    head_sha: str,
) -> PublishIntent | None:
    return load_publish_intent(state_root, repository, head_sha)


def iter_publish_intents(state_root: Path) -> list[PublishIntent]:
    root = Path(state_root) / "publish-intents"
    if not root.is_dir():
        return []
    found: list[PublishIntent] = []
    for path in sorted(root.rglob("*.json")):
        if path.name.endswith(".tmp"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            found.append(PublishIntent.model_validate(data))
        except (json.JSONDecodeError, ValueError, OSError):
            continue
    return found


def find_intent_by_transaction_id(state_root: Path, transaction_id: str) -> PublishIntent | None:
    for intent in iter_publish_intents(state_root):
        if intent.transaction_id == transaction_id or intent.run_id == transaction_id:
            return intent
    return None


def find_intent_by_run_id(state_root: Path, run_id: str) -> PublishIntent | None:
    for intent in iter_publish_intents(state_root):
        if intent.run_id == run_id:
            return intent
    return None
