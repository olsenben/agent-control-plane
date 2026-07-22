# Handoff -- coordinator-handoff-029

## Meta

| Field | Value |
|-------|-------|
| Handoff ID | 029 |
| Date (UTC) | 2026-07-22 |
| Slice / ticket ID | V9 T03 |
| Tip SHA (ACP) | `23f8457` |
| Epic | V9 Agent Observatory |
| `stopped_reason` | `ticket_complete_deploy_gate` |

## Compact return (for boss)

```text
handoff_path: docs/handoff/coordinator-handoff-029.md
ticket: T03
status: Deploy gate
tip_sha: 23f8457
tests: 756 passed
ruff: All checks passed!
blocker: none (NPM proxy_buffering step documented in the slice doc but
  not live-smoked -- no NPM access from this sandbox; app-level
  X-Accel-Buffering/Cache-Control headers are in place regardless and are
  sufficient for direct-to-CT103 deploy-verify smoke)
stopped_reason: ticket_complete_deploy_gate
```

## Slice outcome

- Protected SSE stream (`agent_control/observe/routes.py`,
  `observe_session_stream`) rewritten from V6 T03's fixed-interval poll
  loop to a Redis-notified live tail over `observe.sqlite` (V9 T02),
  implementing hard gate **H4** in order: authorize before the stream
  (unchanged from T05) -> subscribe to the per-run Redis notify channel
  FIRST -> emit `observe.sqlite` history (`projection_sequence > after`,
  `after` = `max(Last-Event-ID, ?after_sequence=)`) -> drain Redis
  notifications while connected (mid-stream auth re-check every
  iteration, preserving V8 T03's revoke/rotate guarantee) -> for each
  notification, re-read `observe.sqlite` and dedupe by
  `projection_sequence`, never trusting the notify payload as display
  data.
- Redis outage degrades live tailing only: if `subscribe()` fails (or the
  shared circuit breaker is already open), the route still serves complete
  `observe.sqlite` history, then emits `event: degraded` + `event: end` and
  returns -- the `EventSource` client's automatic `Last-Event-ID` retry
  gets a fully caught-up history on every reconnect attempt regardless of
  Redis health.
- New module `agent_control/observe/notify.py`: ids-only publish
  (`run_id`/`projection_sequence`/`observation_id`, never event content)
  with a shared per-`redis_url` circuit breaker (`is_circuit_open`/
  `record_publish_failure`) used by both the publisher (projector) and the
  subscriber (this route) so a down Redis doesn't force every caller to
  separately pay the DNS/connect failure cost.
- `agent_control/observe/projector.py`: `project_event_fail_open` fires the
  notify exactly once per genuinely new row, strictly after the
  `observe.sqlite` write commits (H4: "commit SQLite then publish
  Redis"); isolated from the H7 fail-open projection path so a Redis
  failure is never logged/counted as an `observe.sqlite` projection
  failure. `rebuild_observe_db` (full per-project rescan) intentionally
  skips this hook so a rebuild never floods live subscribers with a
  backlog of historical notifies.
- `agent_control/observe/store.py`: `ObserveStore.get_event_by_sequence`
  added for the notify hook to resolve `observation_id`.
- Response headers: `X-Accel-Buffering: no` + `Cache-Control: no-cache` on
  the streaming response, since Nginx Proxy Manager buffers proxied
  responses by default; the slice doc documents the NPM-side
  `proxy_buffering off;` follow-up for whoever owns that config.
- ADR-0030 accepted; slice doc
  [docs/slice-v9-t03-protected-sse-redis-notify.md](../slice-v9-t03-protected-sse-redis-notify.md).
- New tests: `tests/test_v9_t03_protected_sse.py` (14 tests) using a new
  in-process fake-Redis pub/sub test double (`tests/_fake_redis.py`, not
  collected as a test module) that lets one patched `redis.Redis.from_url`
  drive a real publish/subscribe round trip -- covering subscribe-before-
  history-read ordering, `Last-Event-ID`/`?after_sequence=` cursor
  resolution (incl. "take the higher of the two"), Redis-outage
  degrades-live-only, a row delivered live via notify that was not yet in
  history, duplicate-notify dedupe, a bogus/nonexistent notified sequence
  never producing a phantom frame, a mismatched-`run_id` notify ignored,
  and the H4 race itself (a row committed and notified in the exact window
  right as the stream subscribes is captured exactly once).
- `tests/test_v8_t03_mid_sse_revoke.py` (mid-stream credential
  revoke/rotate, V8 T03) ported to the new Redis-based live loop -- same
  asserted outcome, injection point moved from the old `asyncio.sleep`
  tick to the fake pubsub's first `get_message()` poll; two latent bugs
  found and fixed while porting (fake redis client needs a no-op
  `publish()` so the seed event's own projector-fired notify doesn't trip
  the breaker before the SSE call runs; seeding must happen inside the
  same patched-redis context as the SSE call, not before it).
- `tests/conftest.py`: new autouse fixture resets
  `agent_control.observe.notify`'s process-global, per-`redis_url` circuit
  breaker before every test, so suite ordering/timing can never leak one
  test's real-connection failure into another test's mocked-redis
  expectations.
- `ruff check .` clean; full suite `756 passed` (up from 755 passed / 2
  failed pre-existing-regression baseline measured at the start of this
  ticket -- the 2 failing tests were the not-yet-ported V8 T03 mid-SSE
  tests, now fixed and passing).
- Committed on `main` in two commits on top of `1f71bf6`: `3cb17ef`
  (docs-only V9 T05 / V8 residual-QA deploy-verify closeout that was
  already decided but not yet committed when this ticket started) and
  `23f8457` (this ticket's code + tests + docs). Push pending this
  handoff's ledger commit (matching the established wave pattern).

## Explicit non-goals honored

- No Jinja/HTMX five-panel UI (T04) -- the existing HTML page's embedded
  `EventSource` snippet already pointed at
  `/api/observe/v1/sessions/{run_id}/stream` (from T05) and is unchanged.
- No `extra_tabs` / `OBSERVE_PUBLIC_BASE_URL` (T06).
- No change to `observe.sqlite`'s schema or identity/sequence rules (T02,
  H3) -- only a notify side channel and reuse of T02's existing keyset
  pagination helper.
- No change to the auth response matrix (T05, H2) -- `observe_session_stream`
  calls the same `require_observe_identity` / `authorize_repo_read`
  functions in the same order as before this ticket.
- No live NPM smoke -- documented as a human follow-up in the slice doc;
  this sandbox has no NPM access.

## Evidence pointers

- Code: `src/agent_control/observe/notify.py` (new),
  `src/agent_control/observe/projector.py` (diff),
  `src/agent_control/observe/routes.py` (diff),
  `src/agent_control/observe/store.py` (diff: `get_event_by_sequence`)
- Tests: `tests/test_v9_t03_protected_sse.py`, `tests/_fake_redis.py`,
  `tests/test_v8_t03_mid_sse_revoke.py` (diff), `tests/conftest.py` (diff)
- Docs: ADR-0030, `docs/slice-v9-t03-protected-sse-redis-notify.md`

## Decisions the next coordinator must honor

1. `observe.sqlite` is the sole system of record for the SSE endpoint;
   Redis notify payloads are ids-only and must never be rendered or
   trusted directly -- any future change to this route must keep
   re-reading `observe.sqlite` for the actual frame content.
2. The SSE cursor is always the durable `projection_sequence` (H3) --
   never introduce a timestamp-based or in-memory-only cursor.
3. `agent_control.observe.notify.is_circuit_open` /
   `record_publish_failure` are the shared breaker API between any future
   Redis publisher and subscriber in this subsystem -- do not add a second,
   independent breaker.
4. Any new test that exercises this SSE route or the notify publish path
   must either patch `redis.Redis.from_url` for its entire body (including
   any seed/setup calls that might themselves publish) or rely on the
   `tests/conftest.py` autouse breaker reset -- both are already in place,
   but a test that lets a real connection attempt happen outside a patched
   context can still burn multiple seconds on DNS resolution.
5. T04 (five-panel UI) is the first consumer of this stream from a real
   browser `EventSource`; it must rely on `Last-Event-ID` reconnect
   behavior rather than inventing its own client-side cursor tracking.

## Next coordinator: first actions

1. `git push origin main` (this handoff + ledger commit, on top of
   `23f8457`) so CT102 Actions runs per the homelab deploy pattern.
2. Deploy-verify on CT103 (+CT104 if applicable): confirm CI green on the
   pushed tip, `/readyz` still ok, and a smoke of the protected SSE stream
   (history replay via `?after_sequence=0`, then confirm a live event
   arrives after a new ledger append for that run, e.g. via
   `agentctl observe rebuild` or a fresh session) before flipping T03 to
   Done. Include the NPM `proxy_buffering` check from the slice doc if NPM
   access is available at deploy-verify time; otherwise mark that item
   N/A for this deploy-verify per the slice doc's guidance.
3. Start T04 (Jinja+HTMX five-panel UI; text-safe; no-JS timeline) per the
   epic spine (`T01 -> T02 -> T05 -> T03 -> T04 -> T06 -> T07 ∥ T08`); T04
   should consume this ticket's `Last-Event-ID`-based reconnect contract
   from a real `EventSource` rather than re-deriving SSE cursor logic.

## Open risks (one line each)

- NPM `proxy_buffering off;` for this path is documented but not
  live-verified from this sandbox; if the deployed Observatory sits behind
  NPM, confirm this during deploy-verify or the first time a real browser
  is pointed at the five-panel UI (T04).
- The live-loop's per-iteration Redis poll (`pubsub.get_message(timeout=2.0)`)
  runs via `asyncio.to_thread`, adding one thread-pool round trip per idle
  tick; acceptable at homelab connection-count scale, called out in
  ADR-0030 for future revisit under real concurrent-viewer load.
