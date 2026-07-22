"""Redis id-only projection notify channel (V9 T03; H4 steps 2 and 5).

The projector publishes ONLY ids -- ``run_id``, ``projection_sequence``,
``observation_id`` -- to a per-run Redis pub/sub channel, and only *after*
the observe.sqlite write has already committed (H4 step 2: "commit SQLite
then publish Redis ids-only"). The notify payload is never display data and
a subscriber must never render it directly; it exists purely to tell an
already-subscribed SSE stream "go re-read observe.sqlite" (H4 step 5:
"fetch authoritative SQLite row").

Publishing is best-effort and circuit-broken: a single failed publish opens
a short per-process, per-``redis_url`` cooldown so a down/unreachable Redis
degrades cheaply instead of paying a repeated connect timeout on every
single ledger append while Redis is unavailable. Ledger appends and
observe.sqlite projection (H7) must always succeed independent of Redis
health; this module never raises out of :func:`publish_projection_notify`.
"""

from __future__ import annotations

import json
import logging
import time

logger = logging.getLogger(__name__)

NOTIFY_CHANNEL_PREFIX = "observe:notify:"

# Bound the worst case for a black-holed (not merely "connection refused")
# Redis endpoint -- without this, a single stalled TCP handshake could block
# every ledger append for the OS-default connect timeout.
CONNECT_TIMEOUT_SECONDS = 1.0
SOCKET_TIMEOUT_SECONDS = 1.0

# Per-process circuit breaker: after one publish failure for a given
# redis_url, skip further attempts for this many seconds rather than paying
# a repeated connect timeout on every subsequent ledger append. A DNS
# lookup failure for an unreachable hostname can itself take multiple
# seconds (observed ~2s in some sandboxes) before the OS resolver even
# returns "unknown host" -- this cooldown has to be comfortably longer than
# that single failure cost, not just the TCP connect timeout, or a modest
# stream of ledger appends spread a few seconds apart during a Redis outage
# would each pay that cost again.
FAILURE_COOLDOWN_SECONDS = 30.0

_last_failure_at: dict[str, float] = {}


def notify_channel(run_id: str) -> str:
    """Per-run Redis pub/sub channel used for both publish and subscribe."""
    return f"{NOTIFY_CHANNEL_PREFIX}{run_id}"


def _circuit_open(redis_url: str) -> bool:
    failed_at = _last_failure_at.get(redis_url)
    return failed_at is not None and (time.monotonic() - failed_at) < FAILURE_COOLDOWN_SECONDS


def is_circuit_open(redis_url: str) -> bool:
    """Public read of the circuit-breaker state for *redis_url*.

    Shared with the SSE route (:mod:`agent_control.observe.routes`) so a
    persistently-unreachable Redis doesn't make every new SSE connection
    separately pay the same DNS/connect failure cost this module already
    paid once -- a fresh SSE ``subscribe()`` attempt can check this first
    and go straight to the degraded path.
    """
    return _circuit_open(redis_url)


def record_publish_failure(redis_url: str) -> None:
    """Open the circuit for *redis_url* without going through a publish call.

    Used by the SSE route when its own ``subscribe()`` attempt fails, so
    that failure also short-circuits subsequent publish attempts (and
    subsequent SSE connections) for the cooldown window -- one shared
    breaker per ``redis_url``, regardless of which caller tripped it.
    """
    _last_failure_at[redis_url] = time.monotonic()


def publish_projection_notify(
    redis_url: str,
    *,
    run_id: str,
    projection_sequence: int,
    observation_id: int,
) -> bool:
    """Best-effort ids-only publish. Returns ``True`` on success, ``False`` otherwise.

    Never raises. The observe.sqlite row this notify describes has *already*
    committed (H4 step 2) by the time this is called -- a notify failure
    must be indistinguishable from "no subscriber happened to be listening",
    never a reason to retry or undo the write it describes.
    """
    if _circuit_open(redis_url):
        return False
    try:
        import redis as redis_lib

        client = redis_lib.Redis.from_url(
            redis_url,
            socket_connect_timeout=CONNECT_TIMEOUT_SECONDS,
            socket_timeout=SOCKET_TIMEOUT_SECONDS,
        )
        try:
            payload = json.dumps(
                {
                    "run_id": run_id,
                    "projection_sequence": projection_sequence,
                    "observation_id": observation_id,
                }
            )
            client.publish(notify_channel(run_id), payload)
        finally:
            client.close()
    except Exception:
        _last_failure_at[redis_url] = time.monotonic()
        logger.warning(
            "observe_notify_publish_failed run_id=%s projection_sequence=%s",
            run_id,
            projection_sequence,
            exc_info=True,
        )
        return False
    _last_failure_at.pop(redis_url, None)
    return True
