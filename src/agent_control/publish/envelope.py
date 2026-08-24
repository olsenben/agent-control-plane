"""Bind task_envelope.v1 at session/fix dispatch. CT103 durable sidecar only."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from agent_control.memory.preflight_artifacts import session_artifact_dir
from agent_control.transaction.admission import FROZEN_C_HASH
from agent_control.transaction.config import load_transaction_control_config
from agent_control.transaction.identity import (
    agent_worker,
    attribution,
    control_plane,
    human_initiator,
)
from agent_shared.hash_utils import canonical_json_hash
from agent_shared.models.agent_session import AgentSession
from agent_shared.models.jobs import RLMJob
from agent_shared.models.transaction.task import (
    PolicyContext,
    RequestedChange,
    TaskEnvelope,
    task_digest_for,
)
from agent_shared.project_ids import split_project

TASK_ENVELOPE_FILENAME = "task_envelope.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def tenant_org_from_project(project: str) -> tuple[str, str]:
    owner, _repo = split_project(project)
    return owner, owner


def policy_digest_for(*, policy_id: str, policy_version: str) -> str:
    return canonical_json_hash(
        {
            "policy_id": policy_id,
            "policy_version": policy_version,
            "admission_implementation_digest": FROZEN_C_HASH,
        }
    )


def task_envelope_path(state_root: Path, project: str, session_id: str) -> Path:
    return session_artifact_dir(state_root, project, session_id) / TASK_ENVELOPE_FILENAME


def load_task_envelope(
    state_root: Path, project: str, session_id: str
) -> TaskEnvelope | None:
    path = task_envelope_path(state_root, project, session_id)
    if not path.is_file():
        return None
    try:
        return TaskEnvelope.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValueError):
        return None


def persist_task_envelope(
    state_root: Path,
    envelope: TaskEnvelope,
    *,
    session_id: str,
) -> tuple[Path, bool]:
    """Idempotent persist. Existing identical envelope is reused; never mutated."""
    path = task_envelope_path(state_root, envelope.repository, session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = envelope.model_dump_json(indent=2)
    if path.is_file():
        existing = path.read_text(encoding="utf-8")
        if existing == body:
            return path, False
        return path, False
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, path)
    return path, True


def _task_type_for_job(job: RLMJob) -> str:
    intent = job.command_intent
    kind = (intent.kind if intent else "") or ""
    text = " ".join(
        [
            kind,
            (intent.natural_language_task if intent else "") or "",
            (job.risk_class or ""),
        ]
    ).lower()
    if "security" in text or "cwe" in text:
        return "SECURITY_REMEDIATION"
    if kind == "repair":
        return "FUNCTIONAL_MAINTENANCE"
    return "FUNCTIONAL_MAINTENANCE"


def build_task_envelope(
    *,
    session: AgentSession,
    job: RLMJob | None = None,
    changed_files: list[str] | None = None,
    source_sha: str | None = None,
    authorized_files: list[str] | None = None,
    created_at: str | None = None,
) -> TaskEnvelope:
    cfg = load_transaction_control_config()
    project = session.project
    tenant_id, org_id = tenant_org_from_project(project)
    sha = source_sha or session.head_sha
    if len(sha) < 7:
        sha = (sha + "0" * 7)[:7]
    files = list(authorized_files or changed_files or [])
    if not files and job is not None and job.fix_authorization is not None:
        files = list(job.fix_authorization.allowed_files)
    human = human_initiator(session.invoked_by or "unknown")
    worker = agent_worker("agentworker")
    identity = attribution(
        on_behalf_of=human,
        executed_by=worker,
        authorized_by=control_plane(),
    )
    task_type = _task_type_for_job(job) if job is not None else "FUNCTIONAL_MAINTENANCE"
    policy_id = cfg.auto_admit_policy_id
    policy_version = "v1"
    digest = policy_digest_for(policy_id=policy_id, policy_version=policy_version)
    policy = PolicyContext(
        policy_id=policy_id,
        policy_version=policy_version,
        policy_digest=digest,
        admission_implementation_digest=FROZEN_C_HASH,
    )
    provider_task_id = str(session.subject_number)
    task_id = f"task:{session.session_id}"
    summary = "typed session task"
    if job is not None and job.command_intent is not None:
        summary = (
            job.command_intent.natural_language_task
            or job.command_intent.work_item_id
            or summary
        )
    classes: list[str] = ["PRODUCTION_SOURCE_CHANGE"]
    if task_type == "SECURITY_REMEDIATION":
        classes.append("SECURITY_FINDING_TASK")
    payload = {
        "schema_version": "task_envelope.v1",
        "task_id": task_id,
        "tenant_id": tenant_id,
        "org_id": org_id,
        "repository": project,
        "source_sha": sha,
        "task_provider": "GITEA_ISSUE",
        "provider_task_id": provider_task_id,
        "human_initiator": human.model_dump(mode="json"),
        "initiator_identity": human.identity_id,
        "identity": identity.model_dump(mode="json"),
        "task_type": task_type,
        "requested_change": RequestedChange(summary=summary or "fix").model_dump(mode="json"),
        "authorized_change_classes": classes,
        "authorized_files": files,
        "authorized_surfaces": [],
        "security_finding_ids": [],
        "policy_context": policy.model_dump(mode="json"),
        "created_at": created_at or session.created_at or utc_now(),
    }
    envelope = TaskEnvelope.model_validate(
        {**payload, "task_digest": task_digest_for(payload)}
    )
    return envelope


def bind_task_envelope_at_dispatch(
    state_root: Path,
    *,
    session: AgentSession,
    job: RLMJob,
    changed_files: list[str] | None = None,
) -> TaskEnvelope:
    """Persist task_envelope.v1 next to the session. Not copied into worker payloads."""
    existing = load_task_envelope(state_root, session.project, session.session_id)
    if existing is not None:
        return existing
    envelope = build_task_envelope(
        session=session,
        job=job,
        changed_files=changed_files,
        source_sha=job.target_sha or session.head_sha,
    )
    persist_task_envelope(state_root, envelope, session_id=session.session_id)
    return envelope
