---
id: ADR-0030
title: Protected Observatory SSE is subscribe-first with Redis ids-only notify over an authoritative SQLite read
status: accepted
date: 2026-07-22
owners:
  - platform
scope:
  globs:
    - "src/agent_control/observe/routes.py"
    - "src/agent_control/observe/notify.py"
    - "src/agent_control/observe/projector.py"
    - "src/agent_control/observe/store.py"
  symbols:
    - observe_session_stream
    - publish_projection_notify
    - notify_channel
    - project_event_fail_open
    - ObserveStore.get_event_by_sequence
decision_type: architecture
enforcement: hard
risk_level: medium
supersedes: []
superseded_by: []
review_after: 2026-10-22
agent_visibility:
  - review
  - developer
---

# Context

V6 T03 shipped a working but poll-cadence SSE endpoint for the Observatory:
each connection woke on a fixed `asyncio.sleep` tick and re-scanned its
source for anything new. V9 T02 replaced that source with `observe.sqlite`
(a durable, per-run-sequenced, display-safe projection -- ADR-0028). This
ticket (V9 T03) introduces Redis as a live-notify transport so the SSE
endpoint can push updates promptly instead of waiting out a poll interval,
while satisfying the epic's hard gate **H4** (protected SSE, subscribe
before history, authoritative re-read, dedupe by durable sequence). Redis is
already present in this deployment (queue broker for other subsystems); this
adds its pub/sub feature as a new architectural dependency for the
Observatory specifically, which is why this warrants a record distinct from
ADR-0028/0029:

1. A caller must never see a 200 SSE stream open before authorization is
   checked (unchanged invariant from T05/V8 T03; this ticket must preserve
   it under a different internal implementation).
2. The classic subscribe-vs-read race must be closed: if "subscribe to
   live updates" happens *after* "read current history", an event
   committed in that gap is silently lost forever (no poll will ever look
   for it again once the cursor has moved past its position, and no live
   notify will fire before the subscription exists to catch it).
3. Redis pub/sub is at-most-once and holds no history -- a message with no
   subscriber listening is simply gone, and pub/sub delivers no delivery
   guarantee, ordering guarantee, or retry semantics on its own. Anything
   resembling "the durable record of what happened" must never live only in
   a pub/sub payload.
4. `observe.sqlite`'s Last-Event-ID-compatible cursor is `projection_sequence`
   (H3, monotonic per `run_id`, established by ADR-0028) -- SSE's own
   `id:`/`Last-Event-ID` reconnection contract must reuse that exact value,
   not a wall-clock timestamp or a separately-maintained counter, or a
   reconnecting client could re-derive a different, inconsistent notion of
   "what have I already seen" than what the store itself considers durable.
5. Redis being unreachable must degrade gracefully -- this Observatory
   surface's core promise (accurate history) does not depend on Redis at
   all; only the "push it to me the instant it happens" convenience does.

# Decision

1. **Redis pub/sub carries ids only, never display data.** The projector
   (`project_event_fail_open` -> `_notify_new_row`) publishes exactly
   `{run_id, projection_sequence, observation_id}` as JSON to a per-run
   channel (`notify_channel(run_id)` = `observe:notify:{run_id}`), published
   only *after* the `observe.sqlite` write for that row has already
   committed ("commit SQLite then publish Redis", per the epic's H4 wording
   verbatim). A subscriber must always treat a received notify as nothing
   more than "go re-read `observe.sqlite`" -- `_drain_new_rows` in
   `routes.py` re-fetches by paging `list_events_for_run(after=last)` rather
   than ever rendering fields out of the notify payload itself. This means a
   notify naming a bogus/fabricated `projection_sequence`, or a stale/
   duplicate notify for an already-delivered row, can never produce an
   incorrect or duplicate frame -- the store, not the message, decides what
   gets emitted.
2. **Subscribe happens before the first history read, every connection,
   with no exception.** `observe_session_stream`'s generator calls
   `pubsub.subscribe(notify_channel(run_id))` first, then runs the initial
   `_drain_new_rows` history replay. Anything committed in between is
   guaranteed to appear at least once: either the history replay's read
   (which runs after the subscribe, so it sees the row) or the notify (which
   the now-active subscription is guaranteed to receive) or both --
   duplication across those two paths is closed by (1)'s
   dedupe-by-`projection_sequence` rule, so double-delivery in that race
   window is harmless by construction rather than avoided by careful timing.
3. **`observe.sqlite` remains the sole system of record; Redis is a
   convenience notification transport only.** No code path ever treats "the
   notify arrived" as sufficient to emit a frame, and no code path ever
   treats "the notify didn't arrive" as evidence that nothing changed. This
   is why a full Redis outage is explicitly scoped as degrading *live
   tailing only*: the endpoint still serves complete, correct history from
   `observe.sqlite` on every request/reconnect regardless of Redis's health,
   announces the degradation via `event: degraded`, and ends the stream so
   the client's `EventSource` retries (with `Last-Event-ID`) rather than
   hanging open with no live updates and no signal why.
4. **One cursor, two names.** The SSE `id:` field and the query alias
   `?after_sequence=` both mean the store's `projection_sequence` for that
   `run_id` -- never a timestamp, never a separate stream-local counter.
   `Last-Event-ID` (what a real `EventSource` actually sends on
   reconnect) and `?after_sequence=` (an explicit alias for non-browser
   callers, e.g. a CLI tailing the same endpoint) are resolved to the same
   cursor by taking whichever is higher when both are present, so a caller
   can never accidentally regress below a point it has already consumed by
   supplying a stale query parameter alongside a newer header.
5. **Best-effort, circuit-broken publish; independent failure domain from
   the primary projection.** `publish_projection_notify` never raises and
   is called from a `try/except` in `_notify_new_row` that is separate from
   the `observe.sqlite` write's own `try/except` in
   `project_event_fail_open` -- a Redis outage must never be logged,
   counted, or reasoned about as an `observe.sqlite` projection failure
   (H7 continues to mean only "the ledger append itself must never fail
   because of the secondary store"; Redis is a tertiary concern one layer
   further out). A single failed publish or subscribe opens a 30-second,
   per-process, per-`redis_url` cooldown (`agent_control.observe.notify`'s
   module-level breaker) shared between the publish side and the SSE
   subscribe side, so a sustained outage does not force every subsequent
   ledger append and every subsequent SSE connection attempt to separately
   re-pay a DNS/connect timeout.
6. **`rebuild_observe_db`'s full rescan bypasses the notify hook entirely**
   by calling `project_ledger_event` directly instead of
   `project_event_fail_open` -- a historical full-project rebuild must never
   flood every currently-open SSE connection with a backlog of stale
   "something changed" signals for rows those connections may have already
   seen via their own history read.

# Consequences

- Positive: closes the classic "subscribe after read" SSE race by
  construction (dedupe, not careful sequencing, is the actual safety
  property), matching the epic's H4 gate exactly.
- Positive: Redis's existing role in this deployment (queue broker) is
  reused rather than adding a new infrastructure dependency; the failure
  mode of "Redis is down" already has an established operational meaning
  elsewhere in this system.
- Positive: `observe.sqlite` staying authoritative means this ticket adds no
  new durability requirement on Redis at all -- Redis pub/sub's lack of a
  persistence/replay story is a non-issue here, unlike systems that use
  Redis Streams or a broker as their durable record.
- Negative: the live-tail loop now blocks (off the event loop, via
  `asyncio.to_thread`) on a blocking `pubsub.get_message(timeout=2.0)` call
  per tick rather than a plain `asyncio.sleep` -- one additional thread per
  concurrently open SSE connection with an active live-tail loop. Acceptable
  at homelab scale (few concurrent Observatory viewers); would need
  revisiting (e.g. `redis.asyncio`) if concurrent-viewer count grows
  substantially.
- Negative: one more moving part (a per-run Redis channel) to reason about
  operationally, though it is explicitly non-load-bearing for correctness --
  an operator can `redis-cli` a channel to sanity-check "did the projector
  actually publish for this run" without that check being able to give a
  false sense of completeness (the history read is what actually matters).
- Follow-up: the response sets `X-Accel-Buffering: no`, but the CT103 NPM
  (nginx) reverse-proxy's own "Block Common Exploits" / custom location
  config still needs a human check for `proxy_buffering off;` on this path
  or live SSE delivery through the public NPM hop will appear to hang until
  disconnect even though the app tier streams correctly -- see
  `docs/slice-v9-t03-protected-sse-redis-notify.md`'s NPM note; not
  verifiable from this sandboxed test environment.
- Follow-up: T04 (five-panel UI) should keep using one `EventSource` per
  page against this same endpoint rather than introducing a second live
  transport; T07/T08 (decisions/CI panels) should project through the same
  `observe.sqlite` + notify path rather than inventing a parallel one.
