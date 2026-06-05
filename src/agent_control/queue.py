"""Redis/RQ queue names and job helpers."""

from __future__ import annotations

from typing import Final, Sequence

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


def deterministic_job_id(queue: str, payload_key: str) -> str:
    return f"{queue}:{payload_key}"


def run_worker(redis_url: str, queue_names: Sequence[str], concurrency: int = 1) -> None:
    """Block and process jobs from the named RQ queues."""
    if concurrency != 1:
        raise ValueError("only concurrency=1 is supported at MVP")
    conn = Redis.from_url(redis_url)
    queues = [Queue(name, connection=conn) for name in queue_names]
    Worker(queues, connection=conn).work()
