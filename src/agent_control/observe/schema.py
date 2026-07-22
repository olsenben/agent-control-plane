"""SQLite schema for observe.sqlite (V9 T02 display-safe event projection).

Two durable tables:

``observe_events``
    One row per projected ``observe_event.v1`` (see
    :mod:`agent_control.observe.safe_display`). Identity is
    ``(run_id, source_kind, source_event_id)`` (H3) so retried/replayed
    ledger appends never duplicate a row. ``projection_sequence`` is a
    monotonic counter scoped to ``run_id`` (H3) -- the durable ordering the
    Observatory timeline/UI/SSE (T03/T04) will page through.

``session_observation``
    Canonical, display-safe mirror of the current
    ``agent_shared.models.agent_session.AgentSession`` record for one
    ``session_id`` (H6). Refreshed opportunistically whenever a
    session-scoped event is projected; always reflects the *current*
    session file, never a stale reconstruction from one event's payload.

``observe_watermark``
    Informational per-project rebuild bookkeeping (last ledger_sequence
    seen, row counts) -- not required for correctness (rebuild always
    rescans the full ledger for the requested project) but useful for
    `agentctl observe rebuild` reporting and future incremental catch-up.
"""

from __future__ import annotations

SCHEMA_VERSION = "observe_sqlite.v1"

DDL = """
CREATE TABLE IF NOT EXISTS observe_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL,
    run_id TEXT NOT NULL,
    session_id TEXT,
    source_kind TEXT NOT NULL,
    source_event_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    known_type INTEGER NOT NULL DEFAULT 0,
    ledger_sequence INTEGER,
    projection_sequence INTEGER NOT NULL,
    recorded_at TEXT,
    projected_at TEXT NOT NULL,
    observe_event_json TEXT NOT NULL,
    UNIQUE(run_id, source_kind, source_event_id),
    UNIQUE(run_id, projection_sequence)
);

CREATE INDEX IF NOT EXISTS idx_observe_events_project_run
    ON observe_events(project, run_id, projection_sequence);

CREATE INDEX IF NOT EXISTS idx_observe_events_session
    ON observe_events(session_id, projection_sequence);

CREATE INDEX IF NOT EXISTS idx_observe_events_project_type
    ON observe_events(project, event_type);

CREATE TABLE IF NOT EXISTS session_observation (
    session_id TEXT PRIMARY KEY,
    project TEXT NOT NULL,
    repo TEXT,
    run_ids_json TEXT NOT NULL DEFAULT '[]',
    subject_kind TEXT,
    subject_number INTEGER,
    command_kind TEXT,
    status TEXT NOT NULL,
    trace_id TEXT,
    correlation_id TEXT,
    risk_level TEXT,
    risk_tags_json TEXT NOT NULL DEFAULT '[]',
    invoked_by TEXT,
    acting_identity TEXT,
    created_at TEXT,
    updated_at TEXT,
    finished_at TEXT,
    terminal_reason_code TEXT,
    terminal_reason_redacted INTEGER NOT NULL DEFAULT 0,
    last_projection_sequence INTEGER NOT NULL DEFAULT 0,
    session_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_session_observation_project
    ON session_observation(project, updated_at);

CREATE TABLE IF NOT EXISTS observe_watermark (
    project TEXT PRIMARY KEY,
    last_ledger_sequence INTEGER NOT NULL DEFAULT 0,
    events_projected INTEGER NOT NULL DEFAULT 0,
    sessions_projected INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT
);
"""
