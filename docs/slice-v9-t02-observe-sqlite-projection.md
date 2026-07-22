# Slice V9 T02 -- observe.sqlite display-safe projection

**Status:** done -- 2026-07-22
**Epic:** V9 Agent Observatory ([boss-ledger-v9.md](handoff/boss-ledger-v9.md))
**Hard gates:** H3 (projection identity/sequence), H6 (canonical AgentSession
state), H7 (fail-open projector); reuses H1 (T01 safe-display)
**ADR:** [0028-observe-sqlite-fail-open-projection.md](adr/0028-observe-sqlite-fail-open-projection.md)
**Depends on:** [slice-v9-t01-observation-event-contract.md](slice-v9-t01-observation-event-contract.md)

## Problem

T01 shipped the safe-display contract and wired it into
`observe/projection.py`, but that builder re-scans every JSON event file
under a project on each call (`agent_control.events.load_project_events`).
T03 (protected SSE) and T04 (five-panel UI) need an indexed, paginatable,
durable store to build on -- and per plan hard gates, that store must exist
*before* T05/T03/T04, must never be able to fail a ledger append (H7), and
must have a stable per-run identity/ordering (H3) so replayed/retried ledger
events and paginated reads behave correctly.

## What shipped

1. **Schema** (`agent_control/observe/schema.py`) -- one shared
   `observe.sqlite` (mirrors the `memory.sqlite`/`graph.sqlite` convention:
   `Settings.observe_db_path` = `agent_state_root/observe/observe.sqlite`):
   - `observe_events` -- one row per projected `observe_event.v1`.
     `UNIQUE(run_id, source_kind, source_event_id)` (H3 identity) and
     `UNIQUE(run_id, projection_sequence)` (H3 per-run ordering), plus
     indexes on `(project, run_id, projection_sequence)`,
     `(session_id, projection_sequence)`, and `(project, event_type)`.
   - `session_observation` -- one row per `session_id`, a canonical,
     display-safe mirror of the *current* `AgentSession` record (H6).
   - `observe_watermark` -- informational per-project rebuild bookkeeping
     (last `ledger_sequence` scanned, row counts).
2. **Store** (`agent_control/observe/store.py`) -- `ObserveStore`: WAL
   journal mode + `busy_timeout` (single-writer CT103, same pattern as
   `MemoryStore`/`GraphStore`), every write wrapped in an explicit
   `BEGIN IMMEDIATE ... COMMIT/ROLLBACK` transaction so the identity check +
   `projection_sequence` assignment can't race within the process.
   Pagination helpers: `list_events_for_run`, `list_events_for_session`
   (keyset pagination via `projection_sequence`), `count_events_for_run`,
   `get_session_observation`. Size warning policy:
   `evaluate_size_warning`/`ObserveStore.size_warning` (default threshold
   512 MiB, `Settings.observe_sqlite_size_warning_mb` /
   `OBSERVE_SQLITE_SIZE_WARNING_MB` env override).
3. **Session snapshot** (`agent_control/observe/session_snapshot.py`) --
   `build_session_observation_row` builds the curated `AgentSession` subset
   for `session_observation`; drops `terminal_reason` (free text) behind a
   fixed placeholder, the same treatment `safe_display`'s classification
   table gives the equivalent ledger `reason` field.
4. **Projector** (`agent_control/observe/projector.py`) --
   `project_ledger_event` (raises on genuine store failure; used directly by
   rebuild) and `project_event_fail_open` (catches everything, logs, never
   raises -- H7). Only events with a resolvable `run_id` are projected
   (mirrors `observe/projection.py`'s existing run/session-scoped matching);
   events without one (approvals keyed by issue number, etc.) are skipped,
   not an error. Every stored row's `observe_event_json` comes from T01's
   `safe_display_event` -- no second raw-payload code path.
5. **Ledger hook** (`agent_control/events.py`) -- `append_event` calls the
   fail-open projector once, only *after* its own atomic JSON write
   succeeds, only on a newly-created append. A second, outer try/except at
   the call site additionally guards against the observe subsystem failing
   to import at all. Nothing on this path can change `append_event`'s
   return value or raise past it.
6. **Rebuild** (`agent_control/observe/rebuild.py` +
   `agentctl observe rebuild --repo <owner/repo> [--db-path PATH]`) -- full
   per-project rescan: delete that project's `observe_events`/
   `session_observation` rows, replay `load_project_events` through the
   same `project_ledger_event`, update the watermark row. Scoped to one
   project (not a whole-file atomic swap) because `observe.sqlite` is a
   shared multi-project database -- see ADR-0028 for why a whole-file swap
   would risk dropping other projects' rows. CLI output reports
   `events_scanned`/`events_projected`/`events_skipped`/`size_bytes`/
   `size_warning`.
7. **No new public routes.** No `/api/observe` or `/observe` route was
   added or modified. Existing V6 Observatory HTTP surface
   (`observe/routes.py`, `observe/auth.py`) is untouched.
8. **Tests** -- `tests/test_v9_t02_observe_store.py` (store-level: identity/
   sequence idempotency, per-run sequence scoping, pagination, size warning,
   session_observation upsert/monotonic sequence) and
   `tests/test_v9_t02_observe_projector.py` (end-to-end via
   `begin_typed_session`/`finalize_session`: rows appear in observe.sqlite,
   poisoned-payload producer-bug scenario never reaches
   `observe_event_json`, session_observation mirrors live `AgentSession` and
   redacts `terminal_reason`, fail-open on store exception and on projector
   import/attribute failure, events without `run_id` are skipped without
   creating the database file, rebuild reproduces live counts and is
   idempotent and project-scoped, `agentctl observe rebuild` CLI smoke).

## Explicit non-goals (deferred to later V9 tickets)

- No Gitea OAuth shell (T05), no protected SSE/Redis id-notify (T03), no
  Jinja/HTMX UI (T04), no `extra_tabs`/`OBSERVE_PUBLIC_BASE_URL` (T06).
- No new `/api/observe` or `/observe` HTTP route -- explicitly out of scope
  per this ticket; pagination helpers exist for T03/T04 to wire in later.
- No background/async queue for projection; it runs synchronously,
  in-process, immediately after the ledger write, bounded by a 5s
  `busy_timeout` before the fail-open catch fires. Acceptable at homelab
  single-writer scale (see ADR-0028 consequences); revisit if CT102 CI
  volume (T08) changes that.
- Approval-lifecycle/CI-matrix events that carry no `run_id` are not
  projected into `observe.sqlite` -- consistent with `observe/projection.py`
  already excluding them from the run/session-scoped timeline, not a new
  gap introduced by this ticket.

## Verification

```
.venv/bin/ruff check .          # All checks passed!
.venv/bin/python -m pytest -q   # 711 passed
```

New test files: `tests/test_v9_t02_observe_store.py` (18 tests),
`tests/test_v9_t02_observe_projector.py` (8 tests).
