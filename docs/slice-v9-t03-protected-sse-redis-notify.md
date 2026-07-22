# Slice V9 T03 -- Protected SSE subscribe-first + Redis id-notify + Last-Event-ID

**Status:** Done -- 2026-07-22 (deploy verify [deploy-verify-v9-t03-20260722.md](handoff/deploy-verify-v9-t03-20260722.md), tip `dae78e3`)
**Epic:** V9 Agent Observatory ([boss-ledger-v9.md](handoff/boss-ledger-v9.md))
**Handoff:** [coordinator-handoff-029.md](handoff/coordinator-handoff-029.md)
**ADR:** [0030-protected-sse-redis-id-notify.md](adr/0030-protected-sse-redis-id-notify.md)
**Depends on:** T05 (done, tip `1f71bf6`)

## Goal

Replace the V6 T03 polling-loop SSE generator with the epic's protected-SSE
contract (hard gate **H4**), so live tailing is push-driven via Redis instead
of a fixed poll cadence, while keeping `observe.sqlite` (T02) as the only
system of record for what actually gets displayed:

1. Authorize before the stream opens -- never a 200 + streamed error for a
   denied caller (unchanged from T05; still enforced ahead of the new logic).
2. Subscribe to the per-run Redis notify channel **first**, before any
   `observe.sqlite` history read.
3. Emit every `observe_events` row with `projection_sequence > after`, where
   `after` is the higher of the `Last-Event-ID` request header and the
   `?after_sequence=` query alias.
4. Drain Redis notifications for as long as the client stays connected.
5. For each notification: never trust its payload as display data -- always
   re-read `observe.sqlite` for the authoritative row(s) and dedupe by
   `projection_sequence`.

Redis outage degrades live tailing only; history stays complete and correct
because `observe.sqlite` (not Redis) is the system of record for this
endpoint.

## What shipped

1. **`agent_control/observe/notify.py`** (new) -- the projector-side half of
   H4 step 2: `publish_projection_notify` publishes an ids-only JSON payload
   (`run_id`, `projection_sequence`, `observation_id`) to a per-run Redis
   pub/sub channel (`notify_channel(run_id)` ->
   `observe:notify:{run_id}`) after the `observe.sqlite` write has already
   committed. Best-effort and never raises; a per-process, per-`redis_url`
   circuit breaker (`FAILURE_COOLDOWN_SECONDS = 30.0`) avoids paying a
   repeated DNS/connect timeout on every ledger append while Redis is down.
   `is_circuit_open` / `record_publish_failure` are shared with the SSE route
   so a persistently-unreachable Redis short-circuits new SSE subscribe
   attempts to the degraded path immediately instead of each one separately
   re-discovering the same outage.
2. **`agent_control/observe/projector.py`** (`project_event_fail_open`) --
   on a genuine new row (not an idempotent replay), fires the notify after
   the store write returns. `rebuild_observe_db`'s direct call to
   `project_ledger_event` deliberately bypasses this so a full historical
   rescan never floods live subscribers with a backlog of stale notifies.
   The notify call is isolated in its own `try/except` from the projection
   write's `try/except` -- a Redis failure is a distinct subsystem outcome
   from an `observe.sqlite` projection failure and must never be logged or
   counted as the latter (H7 stays about the primary/secondary store
   relationship only).
3. **`agent_control/observe/store.py`** -- added
   `ObserveStore.get_event_by_sequence(run_id, projection_sequence)`: fetch
   exactly one row by its durable `(run_id, projection_sequence)` identity.
   Used by the projector to resolve the `id` (`observation_id`) for the
   notify payload right after a write.
4. **`agent_control/observe/routes.py`** (`observe_session_stream`) --
   rewritten event generator implementing H4 in order:
   - Auth (`require_observe_identity` + `authorize_repo_read`) still runs
     synchronously before `StreamingResponse` is constructed (unchanged from
     T05).
   - Cursor resolution: `start_after = max(after_sequence query, Last-Event-ID
     header)` -- both name the same durable `projection_sequence`, never a
     timestamp.
   - Subscribe to `notify_channel(run_id)` before the first
     `store.list_events_for_run` call (`is_circuit_open` short-circuits this
     entirely when the breaker is already open).
   - `_drain_new_rows` pages `observe.sqlite` for
     `projection_sequence > last`, updating `last` as it goes -- used both
     for the initial history replay and every subsequent notify-triggered
     re-read, so the "authoritative row, deduped by projection_sequence"
     rule is one code path, not two.
   - On a subscribe failure (or an already-open circuit): emit
     `event: degraded` + `event: end` after the (still-complete) history
     replay and return -- Redis outage never blocks or truncates history.
   - Live-tail loop: bounded iteration count (matches the old polling loop's
     bounded-duration behavior so one connection can't run forever;
     `EventSource` reconnects transparently with `Last-Event-ID`). Each tick
     re-checks auth (permission revoke / shared-token rotation mid-stream,
     same invariant V8 T03 established) and then blocks off the event loop
     (`asyncio.to_thread`) on `pubsub.get_message(timeout=2.0)` instead of a
     fixed `asyncio.sleep` cadence. A message that parses to this `run_id`
     triggers another `_drain_new_rows` call from `last` -- the notify
     payload's own `projection_sequence`/`observation_id` fields are never
     rendered directly, only used as a "something changed, go look" signal.
     A `get_message` failure degrades the same way as a subscribe failure.
   - `X-Accel-Buffering: no` + `Cache-Control: no-cache` response headers
     (see NPM note below).
5. **Tests**:
   - `tests/_fake_redis.py` (new) -- in-process fake `redis.Redis` /
     `PubSub` (`subscribe`, `get_message`, `publish`, `close`) with two
     deterministic race-pinning hooks (`on_subscribe`, one-shot
     `next_first_poll_hook`) and a `queue_pending` helper for "notify that
     raced ahead of the subscribe". Both the route's subscribe and the
     projector's publish patch the same `redis.Redis.from_url`, so tests
     exercise a real publish/subscribe round trip end to end without a live
     Redis server.
   - `tests/test_v9_t03_protected_sse.py` (new, 14 tests) -- one test per H4
     step plus the core race (a row committed right at subscribe time must
     be seen exactly once, never twice, even though its notify is also
     in-flight), a bogus/fabricated notify payload naming a nonexistent
     sequence, a notify naming a different `run_id` (defense in depth; belt
     and suspenders since channels are already per-run), and the
     `Last-Event-ID` vs `?after_sequence=` "take the higher" rule.
   - `tests/test_v8_t03_mid_sse_revoke.py` (updated, 2 tests unchanged in
     intent) -- adapted from hooking `asyncio.sleep` (the old poll cadence)
     to hooking a fake `pubsub.get_message`'s first call, since the live-tail
     loop no longer sleeps on a fixed timer.

## NPM (nginx) buffering note (deploy-time; not smoke-testable from this
environment)

Nginx Proxy Manager buffers proxied responses by default, which silently
defeats SSE live delivery -- the client would see nothing until the
connection closes -- even though this endpoint streams correctly end to end
behind the proxy layer's back. This response now sets
`X-Accel-Buffering: no`, which disables nginx's own response buffering for
this response, but NPM's *proxy host* configuration additionally needs
either "Block Common Exploits" left off for this location or a custom
`proxy_buffering off;` snippet added to the relevant Custom Location /
Advanced tab. This cannot be verified from a sandboxed test environment
without a live NPM instance in front of CT103; the deploy-verify step for
this ticket smokes the header's presence and a same-host (no NPM hop) live
notify round trip, and CT103 NPM config is otherwise out of this ticket's
code-change scope -- flagged here as an explicit follow-up for whoever next
touches the CT103 reverse-proxy config, not silently assumed done. Mark as
**N/A** in deploy-verify if the operator doing that step has no NPM admin
access at that time; this is a documented gap, not a blocking one for
Done criteria (code + tests + deploy verify of the app tier itself).

## Explicit non-goals honored

- No Jinja/HTMX five-panel UI (T04) -- only the existing inline-HTML page's
  embedded `<script>` (already pointed at `/api/observe/v1/...` since T05)
  is unaffected; it still opens one `EventSource` per page load.
- No `extra_tabs` / `OBSERVE_PUBLIC_BASE_URL` (T06).
- No new Observatory routes -- `observe_session_stream` is the same route
  path mounted on both `/api/observe/*` and `/api/observe/v1/*` since T05;
  only its internal generator changed.
- No change to the `observe.sqlite` schema (H3 identity/sequence columns are
  unchanged from T02) -- only one new read helper
  (`get_event_by_sequence`) was added.

## Verification

```
.venv/bin/ruff check .          # All checks passed!
.venv/bin/python -m pytest -q   # 756 passed
```

New test files: `tests/test_v9_t03_protected_sse.py` (14 tests),
`tests/_fake_redis.py` (fixture, no tests of its own). Updated:
`tests/test_v8_t03_mid_sse_revoke.py` (2 tests, same assertions).

## Non-goals

- Replacing Redis pub/sub with a durable queue/stream (Redis Streams,
  outbox table, etc.) -- pub/sub's at-most-once, no-history semantics are
  acceptable here specifically because `observe.sqlite` (not Redis) is the
  durable source of truth and the SSE contract already tolerates a missed
  or duplicate notify by design (H4 steps 3/5).
- A dedicated retention/backpressure policy for very high-volume runs beyond
  the existing bounded-iteration live-tail loop and `limit=500` pagination
  in `_drain_new_rows`.
