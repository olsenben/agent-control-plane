"""Idempotent CI failure evidence collector (Slice 6F.1)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from agent_control.ci.failure_classify import classify_failure
from agent_control.ci.gitea_actions_errors import GiteaActionsApiError
from agent_control.ci.log_sanitize import sanitize_ci_log
from agent_control.config import Settings, get_settings
from agent_control.gitea_client import GiteaClient
from agent_shared.models.ci import (
    EvidenceJobRecord,
    EvidenceStatus,
    FailureEvidenceManifest,
    WorkflowObservation,
)
from agent_shared.repo_identity import split_repo_full_name
from agent_workers.security.redactor import SecretRedactor

logger = logging.getLogger(__name__)

_FAILED_CONCLUSIONS = frozenset({"failure", "cancelled", "canceled", "timed_out", "timeout"})


def evidence_observation_id(
    *,
    owner: str,
    repo: str,
    fix_run_id: str,
    pr_number: int | None,
    expected_head_sha: str,
    workflow_run_id: str,
    workflow_run_attempt: int,
) -> str:
    pr = "" if pr_number is None else str(pr_number)
    payload = "|".join(
        [
            owner,
            repo,
            fix_run_id,
            pr,
            expected_head_sha,
            str(workflow_run_id),
            str(workflow_run_attempt),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def failure_evidence_dir(artifact_root: Path, observation_id: str) -> Path:
    return artifact_root / "ci" / "failure-evidence" / observation_id


def load_manifest(artifact_root: Path, observation_id: str) -> FailureEvidenceManifest | None:
    path = failure_evidence_dir(artifact_root, observation_id) / "manifest.json"
    if not path.is_file():
        return None
    try:
        return FailureEvidenceManifest.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValueError):
        return None


def _write_exclusive(path: Path, data: str | bytes) -> bool:
    """Exclusive-create. Returns True if created, False if already exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        fd = os.open(path, flags, 0o644)
    except FileExistsError:
        return False
    try:
        if isinstance(data, str):
            os.write(fd, data.encode("utf-8"))
        else:
            os.write(fd, data)
    finally:
        os.close(fd)
    return True


def write_manifest_exclusive(artifact_root: Path, manifest: FailureEvidenceManifest) -> bool:
    path = failure_evidence_dir(artifact_root, manifest.evidence_observation_id) / "manifest.json"
    body = json.dumps(manifest.model_dump(mode="json"), indent=2)
    return _write_exclusive(path, body)


def fix_ci_failure_evidence_enabled(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return bool(settings.fix_ci_failure_evidence_enabled)


def ensure_failure_evidence(
    artifact_root: Path,
    *,
    fix_run_id: str,
    repository: str,
    expected_head_sha: str,
    observation: WorkflowObservation,
    run_number: int | None = None,
    settings: Settings | None = None,
    gitea_client: GiteaClient | None = None,
    redactor: SecretRedactor | None = None,
) -> FailureEvidenceManifest:
    """Idempotent: same observation_id returns existing immutable manifest."""
    settings = settings or get_settings()
    owner, repo = split_repo_full_name(repository)
    obs_id = evidence_observation_id(
        owner=owner,
        repo=repo,
        fix_run_id=fix_run_id,
        pr_number=observation.pr_number,
        expected_head_sha=expected_head_sha,
        workflow_run_id=observation.workflow_run_id,
        workflow_run_attempt=observation.run_attempt,
    )
    existing = load_manifest(artifact_root, obs_id)
    if existing is not None:
        return existing

    now = datetime.now(timezone.utc).isoformat()
    base = FailureEvidenceManifest(
        evidence_observation_id=obs_id,
        status="unavailable",
        fix_run_id=fix_run_id,
        repository=repository,
        expected_head_commit_sha=expected_head_sha,
        pr_number=observation.pr_number,
        workflow_run_id=observation.workflow_run_id,
        run_number=run_number,
        workflow_run_attempt=observation.run_attempt,
        workflow_path=observation.path,
        workflow_display_name=observation.display_name,
        collected_at=now,
    )

    client = gitea_client or GiteaClient(settings)
    redactor = redactor or SecretRedactor()
    try:
        jobs = client.list_workflow_run_jobs(
            owner,
            repo,
            observation.workflow_run_id,
            require_nonempty_on_terminal=True,
        )
    except GiteaActionsApiError as exc:
        status: EvidenceStatus
        reasons = [f"jobs_api:{exc.kind}"]
        if exc.kind == "empty_jobs":
            status = "contract_mismatch"
            reasons.append("contract_mismatch")
        else:
            status = "unavailable"
        manifest = base.model_copy(
            update={
                "status": status,
                "reason_codes": reasons,
                "failure_class": "api_unavailable" if status == "unavailable" else "unknown",
            }
        )
        write_manifest_exclusive(artifact_root, manifest)
        return load_manifest(artifact_root, obs_id) or manifest

    failed_jobs = [
        j
        for j in jobs
        if (j.conclusion or "").lower() in _FAILED_CONCLUSIONS
        or (j.status or "").lower() in ("failure", "failed")
    ]
    # If API lists jobs but none marked failed on a failing workflow, still capture all
    targets = failed_jobs or list(jobs)

    job_records: list[EvidenceJobRecord] = []
    bytes_received = 0
    bytes_retained = 0
    lines_retained = 0
    redaction_count = 0
    retained_parts: list[str] = []
    source_lengths: list[int] = []
    has_failed = False

    jobs_dir = failure_evidence_dir(artifact_root, obs_id) / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)

    for job in targets:
        if (job.conclusion or "").lower() in _FAILED_CONCLUSIONS:
            has_failed = True
        try:
            logs = client.download_job_logs(owner, repo, job.job_id)
        except GiteaActionsApiError as exc:
            logger.warning(
                "ci_job_logs_unavailable job_id=%s kind=%s",
                job.job_id,
                exc.kind,
            )
            continue
        sanitized = sanitize_ci_log(
            logs.body,
            source_content_length=logs.source_content_length,
            redactor=redactor,
        )
        rel = f"jobs/{job.job_id}.txt"
        created = _write_exclusive(jobs_dir / f"{job.job_id}.txt", sanitized.text)
        if not created:
            # Parallel writer won — reload if possible later
            pass
        job_records.append(
            EvidenceJobRecord(
                job_id=job.job_id,
                name=job.name,
                status=job.status,
                conclusion=job.conclusion,
                retained_path=rel,
                retained_sha256=sanitized.retained_sha256,
                bytes_retained=sanitized.bytes_retained,
                lines_retained=sanitized.lines_retained,
                window_offsets=sanitized.window_offsets,
            )
        )
        bytes_received += sanitized.bytes_received
        bytes_retained += sanitized.bytes_retained
        lines_retained += sanitized.lines_retained
        redaction_count += sanitized.redaction_count
        retained_parts.append(sanitized.text)
        if sanitized.source_content_length is not None:
            source_lengths.append(sanitized.source_content_length)

    if not job_records:
        manifest = base.model_copy(
            update={
                "status": "unavailable",
                "reason_codes": ["no_job_logs_retained"],
                "failure_class": "api_unavailable",
                "jobs": [],
            }
        )
        write_manifest_exclusive(artifact_root, manifest)
        return load_manifest(artifact_root, obs_id) or manifest

    combined = "\n\n".join(retained_parts)
    combined_hash = hashlib.sha256(combined.encode("utf-8")).hexdigest()
    failure_class = classify_failure(combined, observation_conclusion=observation.conclusion)
    manifest = base.model_copy(
        update={
            "status": "collected",
            "jobs": job_records,
            "bytes_received": bytes_received,
            "bytes_retained": bytes_retained,
            "lines_retained": lines_retained,
            "redaction_count": redaction_count,
            "retained_sha256": combined_hash,
            "source_content_length": sum(source_lengths) if source_lengths else None,
            "failure_class": failure_class,
            "has_terminal_failed_job": has_failed or bool(failed_jobs),
            "reason_codes": [],
        }
    )
    write_manifest_exclusive(artifact_root, manifest)
    return load_manifest(artifact_root, obs_id) or manifest
