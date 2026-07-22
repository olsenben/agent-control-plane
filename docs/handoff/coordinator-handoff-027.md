# Handoff -- coordinator-handoff-027

## Meta

| Field | Value |
|-------|-------|
| Handoff ID | 027 |
| Date (UTC) | 2026-07-22 |
| Slice / ticket ID | V9 T02 |
| Tip SHA (ACP) | `41bad77` |
| Epic | V9 Agent Observatory |
| `stopped_reason` | `ticket_complete_deploy_gate` |

## Compact return (for boss)

```text
handoff_path: docs/handoff/coordinator-handoff-027.md
ticket: T02
status: Deploy gate
tip_sha: 41bad77
tests: 711 passed
ruff: All checks passed!
blocker: none
stopped_reason: ticket_complete_deploy_gate
```

## Slice outcome

- `observe.sqlite` display-safe projection store
  (`agent_control/observe/{schema,store}.py`): `observe_events`
  (`UNIQUE(run_id, source_kind, source_event_id)` +
  `UNIQUE(run_id, projection_sequence)`, H3) and `session_observation`
  (canonical `AgentSession` mirror, H6), WAL + `busy_timeout`, every write in
  its own `BEGIN IMMEDIATE` transaction. Pagination helpers
  (`list_events_for_run`/`list_events_for_session`/`get_session_observation`)
  and a size-warning policy (`OBSERVE_SQLITE_SIZE_WARNING_MB`, default
  512 MiB) ship as library functions -- **no HTTP route added**, per the
  ticket's explicit surface-freeze instruction.
- `agent_control/observe/projector.py`: `project_event_fail_open` -- called
  from `agent_control.events.append_event` only *after* the ledger's own
  atomic write succeeds, only on a new (non-replay) append. Catches/logs
  everything (store failure, or the observe subsystem failing to import at
  all) so a projection failure can never fail the session/ledger append
  (H7). Only events with a resolvable `run_id` are projected (mirrors
  `observe/projection.py`'s existing run/session-scoped matching); every
  stored row reuses T01's `safe_display_event` -- no second raw-payload path.
- `agent_control/observe/session_snapshot.py`: curated `AgentSession`
  subset for `session_observation`; redacts the one free-text field
  (`terminal_reason`) the same way `safe_display` redacts the equivalent
  ledger `reason` field.
- `agent_control/observe/rebuild.py` + `agentctl observe rebuild --repo
  <owner/repo> [--db-path PATH]`: transactional per-project rescan
  (delete + full replay of `load_project_events` through the same
  projector), reports `events_scanned/projected/skipped`, `size_bytes`,
  `size_warning`. Scoped per-project rather than a whole-file atomic swap
  because `observe.sqlite` is one shared multi-project database (see
  ADR-0028 for the reasoning).
- ADR-0028 accepted; slice doc
  [docs/slice-v9-t02-observe-sqlite-projection.md](../slice-v9-t02-observe-sqlite-projection.md).
- New tests: `tests/test_v9_t02_observe_store.py` (18 tests, store-level
  identity/sequence/pagination/size-warning),
  `tests/test_v9_t02_observe_projector.py` (8 tests, end-to-end through
  `begin_typed_session`/`finalize_session`, poisoned-payload producer-bug
  scenario, fail-open on store exception and on projector-attribute
  failure, run-idless events skipped without creating the db file, rebuild
  idempotency/scoping, CLI smoke).
- `ruff check .` clean; full suite `711 passed` (was 685 before this
  ticket; +26).
- Committed on `main` (`41bad77`) and pushed to `origin/main` so CT102
  Actions runs per the homelab deploy pattern.

## Explicit non-goals honored

- No `/api/observe` or `/observe` route registered or modified -- existing
  V6 routes (`observe/routes.py`, `observe/auth.py`) untouched, per the
  ticket's CRITICAL instruction not to expand the public surface.
- No Gitea OAuth shell (T05), no protected SSE/Redis id-notify (T03), no
  Jinja/HTMX UI (T04), no `extra_tabs`/`OBSERVE_PUBLIC_BASE_URL` (T06).
- No background/async worker queue for projection -- runs synchronously,
  in-process, fail-open, immediately after the ledger write (see ADR-0028
  consequences for the latency/scale tradeoff this accepts).

## Evidence pointers

- Code: `src/agent_control/observe/schema.py`,
  `src/agent_control/observe/store.py`,
  `src/agent_control/observe/session_snapshot.py`,
  `src/agent_control/observe/projector.py`,
  `src/agent_control/observe/rebuild.py`,
  `src/agent_control/events.py` (diff only, `append_event` hook),
  `src/agent_control/config.py` (diff only, `observe_db_path` +
  `observe_sqlite_size_warning_*`),
  `src/agent_control/cli.py` (diff only, `agentctl observe rebuild`)
- Tests: `tests/test_v9_t02_observe_store.py`,
  `tests/test_v9_t02_observe_projector.py`
- Docs: ADR-0028, `docs/slice-v9-t02-observe-sqlite-projection.md`

## Decisions the next coordinator must honor

1. `ObserveStore` is the single write/read choke point for `observe.sqlite`
   -- no future ticket should open a second `sqlite3.connect` against this
   file or duplicate the identity/sequence logic.
2. T03 (protected SSE) should read through `ObserveStore`'s pagination
   helpers (or extend them), not re-implement pagination against raw SQL,
   and must not introduce a public route that bypasses `safe_display`
   (every row already carries `observe_event_json` from
   `safe_display_event` -- there is no raw payload to accidentally expose,
   but a naive route could still leak `session_observation.session_json`'s
   full field set without re-checking whether new fields need redaction).
3. `agentctl observe rebuild` is project-scoped and safe to run repeatedly
   (it deletes that project's rows first); it is not yet wired into any
   scheduled/automatic catch-up job -- that is a T03/T08 decision, not
   assumed here.
4. `observe.sqlite` size-warning threshold
   (`OBSERVE_SQLITE_SIZE_WARNING_MB`, default 512) is advisory only (logs/
   CLI output); no retention/pruning policy exists yet. If T08 (CT102 CI
   volume) meaningfully increases event volume, revisit before assuming
   unbounded growth is fine.

## Next coordinator: first actions

1. Confirm CT102 Actions run green on tip `41bad77` (push already done).
2. Flip T02 -> Done in `boss-ledger-v9.md` once deploy verification (CT102
   CI green, and/or CT103 homelab smoke if the boss requires it for this
   ticket, matching the T01 pattern) is recorded.
3. Start T05 (Gitea OAuth shell + 401/redirect/403/503; mount protected
   routes) per the epic spine (`T01 -> T02 -> T05 -> T03 -> T04 -> T06 ->
   T07 || T08`).

## Open risks (one line each)

- Projection runs synchronously in the request/dispatch path; a slow or
  lock-contended `observe.sqlite` adds latency (bounded by the 5s
  `busy_timeout`) before the fail-open catch fires -- acceptable at
  homelab scale today, worth revisiting once T08 adds CT102 CI volume.
- `session_observation.session_json` carries the full curated
  `AgentSession` field set (minus `terminal_reason`); if a future
  `AgentSession` field addition carries free text, `session_snapshot.py`'s
  allowlist-by-omission must be updated at the same time, mirroring the
  discipline T01 established for `safe_display`'s per-type table.
