"""In-process fake Redis pub/sub for V9 T03 protected-SSE tests.

Real Redis is never reachable from unit tests. This fakes just enough of
the ``redis.Redis`` / ``redis.client.PubSub`` surface that
``agent_control.observe.routes.observe_session_stream`` (subscriber) and
``agent_control.observe.notify.publish_projection_notify`` (publisher) use --
``pubsub()``, ``subscribe()``, ``get_message()``, ``publish()``, ``close()``
-- and routes ``publish()`` calls to every ``FakePubSub`` currently
subscribed to that channel, so tests can exercise a true publish/subscribe
round trip (projector -> notify -> SSE) entirely in-process, plus a couple
of deterministic hooks for pinning down otherwise-racy timing (subscribe-
before-history-read; a write that lands exactly at/after subscribe time).

Usage::

    broker = FakeRedisBroker()
    with patch("redis.Redis.from_url", fake_redis_from_url(broker)):
        ...

To simulate a Redis outage (subscribe-time failure), patch
``redis.Redis.from_url`` directly with a ``side_effect`` instead of using
this module.
"""

from __future__ import annotations

from typing import Any, Callable


class FakePubSub:
    def __init__(self, broker: "FakeRedisBroker") -> None:
        self._broker = broker
        self._queue: list[dict[str, Any]] = []
        self.subscribed_channels: list[str] = []
        self.closed = False
        # One-shot: consumed from the broker at construction time (i.e. at
        # the ``redis_client.pubsub()`` call), fired on this instance's
        # first ``get_message()`` -- lets a test inject a write+publish
        # exactly at "the live loop just started polling" without real
        # concurrency.
        self._first_poll_hook: Callable[[], None] | None = broker.next_first_poll_hook
        broker.next_first_poll_hook = None

    def subscribe(self, channel: str) -> None:
        self.subscribed_channels.append(channel)
        self._broker._register(channel, self)

    def get_message(self, timeout: float | None = None) -> dict[str, Any] | None:
        if self._first_poll_hook is not None:
            hook, self._first_poll_hook = self._first_poll_hook, None
            hook()
        if self._queue:
            return self._queue.pop(0)
        return None

    def close(self) -> None:
        self.closed = True
        self._broker._unregister(self)


class FakeRedisClient:
    def __init__(self, broker: "FakeRedisBroker") -> None:
        self._broker = broker
        self.closed = False

    def pubsub(self) -> FakePubSub:
        return FakePubSub(self._broker)

    def publish(self, channel: str, message: str) -> None:
        self._broker.publish(channel, message)

    def close(self) -> None:
        self.closed = True


class FakeRedisBroker:
    """In-process stand-in for a real Redis server's pub/sub routing."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[FakePubSub]] = {}
        self._pending: dict[str, list[str]] = {}
        self.publish_log: list[tuple[str, str]] = []
        # Persistent hook: fired every time anything subscribes to any
        # channel (i.e. every ``.subscribe()`` call) -- used to pin down
        # the H4 step 2 "subscribe happens before history is read" order.
        self.on_subscribe: Callable[[str], None] | None = None
        # One-shot hook consumed by the next ``FakePubSub`` created via
        # ``.pubsub()`` (see above).
        self.next_first_poll_hook: Callable[[], None] | None = None

    def _register(self, channel: str, pubsub: FakePubSub) -> None:
        self._subscribers.setdefault(channel, []).append(pubsub)
        for msg in self._pending.pop(channel, []):
            pubsub._queue.append({"type": "message", "data": msg})
        if self.on_subscribe is not None:
            self.on_subscribe(channel)

    def _unregister(self, pubsub: FakePubSub) -> None:
        for subs in self._subscribers.values():
            if pubsub in subs:
                subs.remove(pubsub)

    def publish(self, channel: str, message: str) -> None:
        self.publish_log.append((channel, message))
        for ps in self._subscribers.get(channel, []):
            ps._queue.append({"type": "message", "data": message})

    def queue_pending(self, channel: str, message: str) -> None:
        """Arrange for *message* to be delivered the moment something next
        subscribes to *channel* -- models a publish that raced ahead of a
        not-yet-open subscription."""
        self._pending.setdefault(channel, []).append(message)


def fake_redis_from_url(broker: FakeRedisBroker):
    """Return a callable suitable as ``redis.Redis.from_url``'s replacement."""

    def _from_url(*_args: Any, **_kwargs: Any) -> FakeRedisClient:
        return FakeRedisClient(broker)

    return _from_url


def disconnect_after(n: int):
    """Async ``Request.is_disconnected`` replacement: ``False`` for the first
    *n* calls, ``True`` after -- lets a test end an otherwise-unbounded SSE
    live-tail loop deterministically after a known number of iterations
    instead of waiting out the endpoint's full iteration budget."""
    state = {"count": 0}

    async def _is_disconnected(_self: Any) -> bool:
        state["count"] += 1
        return state["count"] > n

    return _is_disconnected
