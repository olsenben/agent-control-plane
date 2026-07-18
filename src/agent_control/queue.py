"""Redis/RQ queue names and job helpers."""

from __future__ import annotations

import re
from typing import Any, Callable, Final, Sequence

import rq
from redis import Redis
from rq import Queue, Worker

from agent_shared.constants import (
    ALL_QUEUE_NAMES,
    FLOW_QUEUE_NAMES,
    QUEUE_CI_REPAIR,
    QUEUE_PUBLISH,
    QUEUE_RESULTS_INGEST,
    QUEUE_RLM_ROOT,
    prefixed_queue,
)

QUEUE_NAMES: Final[tuple[str, ...]] = ALL_QUEUE_NAMES

STATE_WORKER_MAX_CONCURRENCY: Final[int] = 1
STATE_JOB_ID_PREFIX: Final[str] = "state"
RLM_ROOT_JOB_ID_PREFIX: Final[str] = "rlm-root"
REPORT_JOB_ID_PREFIX: Final[str] = "report"
INGEST_JOB_ID_PREFIX: Final[str] = "ingest"
CI_REPAIR_JOB_ID_PREFIX: Final[str] = "ci-repair"
PUBLISH_JOB_ID_PREFIX: Final[str] = "publish"
DEDUPE_KEY_PREFIX: Final[str] = "rq:dedupe:"
DEDUPE_TTL_SECONDS: Final[int] = 86400


def deterministic_job_id(queue: str, payload_key: str) -> str:
    return f"{queue}-{sanitize_job_id(payload_key)}"


def sanitize_job_id(value: str) -> str:
    """RQ job_id allows only letters, numbers, underscores, and dashes."""
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "-", value)
    return cleaned or "unknown"


def _rq_supports_unique() -> bool:
    parts = rq.__version__.split(".")
    major = int(parts[0])
    minor = int(parts[1]) if len(parts) > 1 else 0
    return (major, minor) >= (2, 8)


def get_redis(redis_url: str) -> Redis:
    return Redis.from_url(redis_url)


def get_queue(name: str, redis_url: str) -> Queue:
    return Queue(prefixed_queue(name), connection=get_redis(redis_url))


def _acquire_dedupe(conn: Redis, job_id: str) -> bool:
    key = f"{DEDUPE_KEY_PREFIX}{job_id}"
    return bool(conn.set(key, "1", nx=True, ex=DEDUPE_TTL_SECONDS))


def _enqueue(
    redis_url: str,
    queue_name: str,
    func,
    job_id: str,
    *args,
    retry_max: int = 0,
    **kwargs,
) -> str | None:
    conn = get_redis(redis_url)
    enqueue_kwargs: dict = {"job_id": job_id}
    if _rq_supports_unique():
        enqueue_kwargs["unique"] = True
    elif not _acquire_dedupe(conn, job_id):
        return None

    queue = Queue(prefixed_queue(queue_name), connection=conn)
    try:
        job = queue.enqueue(func, *args, job_timeout=900, **enqueue_kwargs, **kwargs)
    except Exception as exc:
        if not _rq_supports_unique():
            conn.delete(f"{DEDUPE_KEY_PREFIX}{job_id}")
        # Unique job already present (finished/queued) — treat as dedupe, not crash
        try:
            from rq.exceptions import DuplicateJobError
        except ImportError:  # pragma: no cover
            DuplicateJobError = ()  # type: ignore[misc, assignment]
        if DuplicateJobError and isinstance(exc, DuplicateJobError):
            return None
        raise
    if retry_max:
        job.meta["retry_max"] = retry_max
        job.save_meta()
    return job.id


def enqueue_state_reduction(
    redis_url: str,
    event_id: str,
    project: str,
    state_root: str,
) -> str | None:
    """Enqueue a project state reduction job; return RQ job id or None if deduped."""
    from agent_control.jobs.state import process_state_reduction

    job_id = deterministic_job_id(STATE_JOB_ID_PREFIX, event_id)
    return _enqueue(redis_url, "state", process_state_reduction, job_id, state_root, event_id, project)


def enqueue_rlm_root(redis_url: str, job_payload: dict[str, Any]) -> str | None:
    from agent_workers.jobs.rlm_root import process_rlm_root

    trigger_event_id = job_payload.get("trigger_event_id", "unknown")
    job_id = deterministic_job_id(RLM_ROOT_JOB_ID_PREFIX, trigger_event_id)
    return _enqueue(redis_url, QUEUE_RLM_ROOT, process_rlm_root, job_id, job_payload, retry_max=1)


def enqueue_ci_repair(redis_url: str, job_payload: dict[str, Any]) -> str | None:
    """Deterministic job id: repo + PR + expected_sha + attempt."""
    from agent_workers.jobs.ci_repair import process_ci_repair

    repo = str(job_payload.get("repository") or "unknown")
    pr = job_payload.get("pr_number")
    sha = str(job_payload.get("expected_head_commit_sha") or "unknown")
    attempt = job_payload.get("repair_attempt") or 0
    key = f"{repo}:{pr}:{sha}:{attempt}"
    job_id = deterministic_job_id(CI_REPAIR_JOB_ID_PREFIX, key)
    return _enqueue(redis_url, QUEUE_CI_REPAIR, process_ci_repair, job_id, job_payload, retry_max=1)


def enqueue_report(redis_url: str, run_id: str, job_payload: dict[str, Any]) -> str | None:
    from agent_workers.jobs.report import process_report

    job_id = deterministic_job_id(REPORT_JOB_ID_PREFIX, run_id)
    return _enqueue(redis_url, "report", process_report, job_id, job_payload, retry_max=3)


def enqueue_ingest_inbox_file(
    redis_url: str,
    run_id: str,
    inbox_path: str,
    content_hash: str,
    state_root: str,
) -> str | None:
    from agent_control.jobs.ingest import process_ingest_inbox_file

    job_id = deterministic_job_id(INGEST_JOB_ID_PREFIX, f"{run_id}-{content_hash}")
    return _enqueue(
        redis_url,
        QUEUE_RESULTS_INGEST,
        process_ingest_inbox_file,
        job_id,
        state_root,
        inbox_path,
    )


def enqueue_publish(
    redis_url: str,
    *,
    run_id: str,
    kind: str,
    attempt_id: str,
    bundle_id: str,
    state_root: str,
    extra: dict[str, Any] | None = None,
) -> str | None:
    """Deterministic job id: run_id + kind + attempt_id + bundle_id."""
    from agent_control.jobs.publish import process_publish
    from agent_control.publish.state import publish_job_id

    job_id = publish_job_id(
        run_id=run_id, kind=kind, attempt_id=attempt_id, bundle_id=bundle_id
    )
    payload: dict[str, Any] = {
        "run_id": run_id,
        "kind": kind,
        "attempt_id": attempt_id,
        "bundle_id": bundle_id,
        "state_root": state_root,
    }
    if extra:
        # Only allowlist repair correlation fields from CT103 state — never clone URL
        for key in (
            "expected_head_commit_sha",
            "agent_branch",
            "project",
            "allowed_files",
        ):
            if key in extra:
                payload[key] = extra[key]
    return _enqueue(redis_url, QUEUE_PUBLISH, process_publish, job_id, payload, retry_max=2)


def _rlm_job_exception_handler(job, exc_type, exc_value, traceback) -> bool:
    """Belt-and-suspenders: report terminal failure if runner crashed before normal path."""
    func_name = getattr(job, "func_name", "") or ""
    if "process_rlm_root" not in func_name:
        return True
    try:
        from agent_workers.jobs.rlm_failure_handler import handle_rlm_job_exception

        return handle_rlm_job_exception(job, exc_type, exc_value, traceback)
    except Exception:
        return True


def run_worker(redis_url: str, queue_names: Sequence[str], concurrency: int = 1) -> None:
    """Block and process jobs from the named RQ queues."""
    if concurrency != 1:
        raise ValueError("only concurrency=1 is supported at MVP")
    conn = Redis.from_url(redis_url)
    queues = [Queue(prefixed_queue(name), connection=conn) for name in queue_names]
    handlers: list[Callable[..., bool]] = []
    if QUEUE_RLM_ROOT in queue_names:
        handlers.append(_rlm_job_exception_handler)
    Worker(queues, connection=conn, exception_handlers=handlers or None).work()


def queue_info(redis_url: str) -> dict[str, Any]:
    conn = get_redis(redis_url)
    info: dict[str, Any] = {"queues": {}}
    for name in FLOW_QUEUE_NAMES:
        qname = prefixed_queue(name)
        queue = Queue(qname, connection=conn)
        failed = queue.failed_job_registry.count
        info["queues"][name] = {
            "count": queue.count,
            "failed": failed,
            "prefixed_name": qname,
        }
    return info
