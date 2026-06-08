"""Redis/RQ queue names and job helpers."""

from __future__ import annotations

import re
from typing import Final, Sequence

import rq
from redis import Redis
from rq import Queue, Worker

QUEUE_NAMES: Final[tuple[str, ...]] = (
    "state",
    "snapshot",
    "planner-3080",
    "reviewer-3080",
    "fixer-3080",
    "judge-3080",
    "rlm-3080",
    "worker-2070",
    "summarizer-2070",
    "testwriter-2070",
    "preview",
    "danger-lab",
)

STATE_WORKER_MAX_CONCURRENCY: Final[int] = 1
STATE_JOB_ID_PREFIX: Final[str] = "state"
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
    return Queue(name, connection=get_redis(redis_url))


def _acquire_dedupe(conn: Redis, job_id: str) -> bool:
    key = f"{DEDUPE_KEY_PREFIX}{job_id}"
    return bool(conn.set(key, "1", nx=True, ex=DEDUPE_TTL_SECONDS))


def enqueue_state_reduction(
    redis_url: str,
    event_id: str,
    project: str,
    state_root: str,
) -> str | None:
    """Enqueue a project state reduction job; return RQ job id or None if deduped."""
    from agent_control.jobs.state import process_state_reduction

    job_id = deterministic_job_id(STATE_JOB_ID_PREFIX, event_id)
    conn = get_redis(redis_url)

    enqueue_kwargs: dict = {"job_id": job_id}
    if _rq_supports_unique():
        enqueue_kwargs["unique"] = True
    elif not _acquire_dedupe(conn, job_id):
        return None

    queue = Queue("state", connection=conn)
    try:
        job = queue.enqueue(
            process_state_reduction,
            state_root,
            event_id,
            project,
            **enqueue_kwargs,
        )
    except Exception:
        if not _rq_supports_unique():
            conn.delete(f"{DEDUPE_KEY_PREFIX}{job_id}")
        raise

    return job.id


def run_worker(redis_url: str, queue_names: Sequence[str], concurrency: int = 1) -> None:
    """Block and process jobs from the named RQ queues."""
    if concurrency != 1:
        raise ValueError("only concurrency=1 is supported at MVP")
    conn = Redis.from_url(redis_url)
    queues = [Queue(name, connection=conn) for name in queue_names]
    Worker(queues, connection=conn).work()
