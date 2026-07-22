---
id: ADR-0028
title: observe.sqlite is a fail-open, display-safe secondary projection
status: accepted
date: 2026-07-22
owners:
  - platform
scope:
  globs:
    - "src/agent_control/observe/schema.py"
    - "src/agent_control/observe/store.py"
    - "src/agent_control/observe/projector.py"
    - "src/agent_control/observe/rebuild.py"
    - "src/agent_control/observe/session_snapshot.py"
    - "src/agent_control/events.py"
  symbols:
    - ObserveStore
    - project_ledger_event
    - project_event_fail_open
    - rebuild_observe_db
    - build_session_observation_row
    - append_event
decision_type: data
enforcement: hard
risk_level: high
supersedes: []
superseded_by: []
review_after: 2026-10-22
agent_visibility:
  - review
  - developer
---

# Context

V9 T01 (ADR-0027) established `observe_event.v1` and the `safe_display`
choke point so no Observatory display surface can consume a raw ledger
`payload`. T02 adds the first durable store for that projection --
`observe.sqlite` -- so T03 (protected SSE) and T04 (five-panel UI) have an
indexed, paginatable source instead of re-scanning every JSON event file per
request (`agent_control.events.load_project_events` is already a full
per-project directory walk).

Two risks specific to *durable* storage that T01's in-memory projection
(`observe/projection.py`) did not have to solve:

1. A second write path (JSON ledger file, then sqlite row) means the sqlite
   write can fail independently of the ledger write it derives from. Plan
   hard gate **H7** requires that failure to be invisible to the caller: a
   session/webhook/CI append must never fail because observe.sqlite is
   unavailable, corrupt, or full.
2. Durable rows need a stable identity so retried/replayed ledger events
   (the ledger itself is already idempotent by `event_id`) don't duplicate
   rows, and a stable per-timeline ordering the UI/SSE can page through
   without re-deriving it from `ledger_sequence` + wall-clock tie-breaks
   every time (plan hard gate **H3**).

# Decision

1. **Identity and ordering (H3).** `observe_events` is keyed by
   `UNIQUE(run_id, source_kind, source_event_id)` -- `source_event_id` is
   the ledger's own deterministic `event_id`, so a replayed append is a
   guaranteed no-op insert, not a duplicate row. `projection_sequence` is a
   second `UNIQUE(run_id, projection_sequence)` counter, monotonic *per
   run_id* (not global), assigned inside the same `BEGIN IMMEDIATE`
   transaction as the identity check so the two invariants cannot race
   against each other for the same run.
2. **Scope matches the existing timeline, not "every ledger event."**
   Only events with a resolvable `run_id` (`payload.run_id`, mirroring
   `observe/projection.py`'s existing `_events_for_run` matching) are
   projected. Events keyed by issue/approval-target instead of `run_id`
   (approvals, some CI events) are out of scope for this run/session-scoped
   table by design, not a gap -- `build_observation_projection` never
   included them either.
3. **Fail-open, after the primary write (H7).**
   `agent_control.events.append_event` calls
   `observe.projector.project_event_fail_open` once, only after its own
   atomic ledger write (`os.replace`) has already succeeded, and only on a
   newly-created append (not a replay short-circuit). Every exception from
   the projector -- store failure, or even an import-time failure of the
   optional observe subsystem -- is caught and logged at `append_event`'s
   call site; nothing from this path can change `append_event`'s return
   value or raise past it. This mirrors the existing fail-open secondary
   write pattern already used for the Gitea status-comment projection
   (`session.lifecycle._project_terminal_comment` /
   `observe.comment_projection.project_session_comment`).
4. **Single shared database, transactional per-project rebuild.**
   `observe.sqlite` is one file at `agent_state_root/observe/observe.sqlite`
   holding all projects, mirroring the existing `memory.sqlite`/
   `graph.sqlite` convention (`Settings.memory_db_path` /
   `Settings.graph_db_path`). `agentctl observe rebuild --repo <owner/repo>`
   therefore cannot be a whole-file atomic swap (that would risk dropping
   every *other* project's already-projected rows); instead it deletes and
   fully re-projects only the requested project's rows inside SQLite write
   transactions (`ObserveStore` already wraps every write in
   `BEGIN IMMEDIATE ... COMMIT`), giving the same effective atomicity
   (all-or-nothing per write) without a cross-project blast radius. An
   `observe_watermark` row records the last `ledger_sequence` scanned per
   project for CLI reporting; rebuild correctness does not depend on it
   since it always rescans the full per-project ledger.
5. **Canonical `AgentSession` mirror, not a re-derivation from one event
   (H6).** `session_observation` is refreshed by loading the *current*
   `AgentSession` file (`agent_control.session.storage.load_session`)
   whenever a session-scoped event is projected, not by accumulating fields
   from that event's own payload. Any triggering event converges to the
   same row content regardless of projection order, because the source of
   truth read at refresh time is always "whatever the session file
   currently says."
6. **T01 safe-display reuse, both tables.** `observe_events.observe_event_json`
   stores the `safe_display_event` output (`ObserveEventV1`), never a raw
   payload -- the same choke point T01 wired into `observe/projection.py`.
   `session_observation` stores a curated `AgentSession` subset
   (`observe.session_snapshot.build_session_observation_row`) that drops the
   one free-text field on that model, `terminal_reason`, replacing it with a
   fixed placeholder -- the same treatment `safe_display`'s classification
   table gives the equivalent ledger `reason` field (`redacted`).
7. **No new public routes.** This ticket adds no `/api/observe` or
   `/observe` HTTP surface. `ObserveStore`'s pagination helpers
   (`list_events_for_run`, `list_events_for_session`,
   `get_session_observation`) exist for T03/T04 to consume later; wiring
   them into a route is explicitly deferred.

# Consequences

- Positive: T03 (SSE) and T04 (UI) get an indexed, paginatable timeline
  without re-walking the ledger's JSON files per request, and inherit the
  H1/H3/H6/H7 invariants without re-deriving them.
- Positive: a broken/corrupt/oversized `observe.sqlite` can never take down
  session dispatch, webhook ingestion, or any other ledger-writing code
  path -- worst case, the Observatory falls behind or the CLI `rebuild`
  is needed, never a 5xx on the primary flow.
- Negative: because projection happens synchronously (in-process, not a
  background queue) right after the ledger write, a slow/locked
  `observe.sqlite` adds latency to the caller before the fail-open catch
  fires (bounded by the 5s `busy_timeout`); acceptable at homelab
  single-writer scale, revisit if T08 (CT102 CI volume) changes that.
- Negative: because `observe.sqlite` is a shared multi-project file, one
  project's `agentctl observe rebuild` still takes a brief write lock that
  could delay a concurrent append for a *different* project (WAL mode
  reduces but does not eliminate this).
- Follow-up: T03 must not add a second code path that reads
  `observe_event_json`/raw ledger payload directly; it should read through
  `ObserveStore`'s pagination helpers (or an equivalent) the same way
  `observe/projection.py` is T01/T02's single choke point for the JSON-file
  path.
