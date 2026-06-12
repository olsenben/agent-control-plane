"""Redis/RQ queue names and job helpers."""

from __future__ import annotations

import re
from typing import Any, Final, Sequence

import rq
from redis import Redis
from rq import Queue, Worker

from agent_shared.constants import ALL_QUEUE_NAMES, FLOW_QUEUE_NAMES, QUEUE_RLM_ROOT, prefixed_queue

QUEUE_NAMES: Final[tuple[str, ...]] = ALL_QUEUE_NAMES

STATE_WORKER_MAX_CONCURRENCY: Final[int] = 1
STATE_JOB_ID_PREFIX: Final[str] = "state"
RLM_ROOT_JOB_ID_PREFIX: Final[str] = "rlm-root"
REPORT_JOB_ID_PREFIX: Final[str] = "report"
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
    except Exception:
        if not _rq_supports_unique():
            conn.delete(f"{DEDUPE_KEY_PREFIX}{job_id}")
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


def enqueue_report(redis_url: str, run_id: str, job_payload: dict[str, Any]) -> str | None:
    from agent_workers.jobs.report import process_report

    job_id = deterministic_job_id(REPORT_JOB_ID_PREFIX, run_id)
    return _enqueue(redis_url, "report", process_report, job_id, job_payload, retry_max=3)


def run_worker(redis_url: str, queue_names: Sequence[str], concurrency: int = 1) -> None:
    """Block and process jobs from the named RQ queues."""
    if concurrency != 1:
        raise ValueError("only concurrency=1 is supported at MVP")
    conn = Redis.from_url(redis_url)
    queues = [Queue(prefixed_queue(name), connection=conn) for name in queue_names]
    Worker(queues, connection=conn).work()


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
