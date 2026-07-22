"""SQLite-backed store for the observe_event.v1 display-safe projection (V9 T02).

Single-writer CT103 database: WAL journal mode + a generous ``busy_timeout``
substitute for a dedicated lock manager, matching the existing
``MemoryStore``/``GraphStore`` connection pattern
(:mod:`agent_control.memory.store`, :mod:`agent_control.graph.store`). Every
write is wrapped in an explicit ``BEGIN IMMEDIATE`` transaction so the
identity/sequence invariants (H3) hold even under concurrent callers within
the same process.

This module never receives a raw ledger payload -- callers
(:mod:`agent_control.observe.projector`) pass already display-safe
``observe_event.v1`` JSON (see :mod:`agent_control.observe.safe_display`) and
a curated ``session_observation`` row (see
:mod:`agent_control.observe.session_snapshot`).
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from agent_control.observe.schema import DDL

BUSY_TIMEOUT_MS = 5000

# Homelab-scale size warning default: observe.sqlite is a display-safe
# projection cache, not a system of record -- if it grows past this, either
# the retention story is missing or something is projecting far too much.
DEFAULT_SIZE_WARNING_BYTES = 512 * 1024 * 1024


def observe_db_path(state_root: Path) -> Path:
    """Default observe.sqlite location, mirroring memory.sqlite/graph.sqlite."""
    return state_root / "observe" / "observe.sqlite"


class ObserveStoreError(RuntimeError):
    """observe.sqlite write failure. Callers decide fail-open policy (H7)."""


def evaluate_size_warning(
    size_bytes: int,
    *,
    threshold_bytes: int = DEFAULT_SIZE_WARNING_BYTES,
) -> str | None:
    """Size warning policy: return a human-readable warning once over threshold."""
    if size_bytes <= threshold_bytes:
        return None
    return (
        f"observe.sqlite is {size_bytes / (1024 * 1024):.1f} MiB, over the "
        f"{threshold_bytes / (1024 * 1024):.0f} MiB warning threshold -- "
        "consider retention/rebuild scoping before it grows further"
    )


class ObserveStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=BUSY_TIMEOUT_MS / 1000,
            isolation_level=None,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        try:
            yield conn
        finally:
            conn.close()

    def init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(DDL)

    def size_bytes(self) -> int:
        try:
            return self.db_path.stat().st_size
        except FileNotFoundError:
            return 0

    def size_warning(self, *, threshold_bytes: int = DEFAULT_SIZE_WARNING_BYTES) -> str | None:
        return evaluate_size_warning(self.size_bytes(), threshold_bytes=threshold_bytes)

    # --- event projection (H3: identity + per-run sequence) ---

    def insert_event(
        self,
        *,
        project: str,
        run_id: str,
        session_id: str | None,
        source_kind: str,
        source_event_id: str,
        event_type: str,
        known_type: bool,
        ledger_sequence: int | None,
        recorded_at: str | None,
        observe_event_json: str,
    ) -> int | None:
        """Idempotent insert keyed on (run_id, source_kind, source_event_id).

        Returns the assigned ``projection_sequence`` for a newly-projected
        row, or ``None`` when a row already exists for that identity
        (replay/retry -- not an error).
        """
        self.init_schema()
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                existing = conn.execute(
                    "SELECT 1 FROM observe_events "
                    "WHERE run_id = ? AND source_kind = ? AND source_event_id = ?",
                    (run_id, source_kind, source_event_id),
                ).fetchone()
                if existing is not None:
                    conn.execute("COMMIT")
                    return None
                row = conn.execute(
                    "SELECT COALESCE(MAX(projection_sequence), 0) AS m "
                    "FROM observe_events WHERE run_id = ?",
                    (run_id,),
                ).fetchone()
                sequence = int(row["m"]) + 1
                conn.execute(
                    """
                    INSERT INTO observe_events (
                        project, run_id, session_id, source_kind, source_event_id,
                        event_type, known_type, ledger_sequence, projection_sequence,
                        recorded_at, projected_at, observe_event_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project,
                        run_id,
                        session_id,
                        source_kind,
                        source_event_id,
                        event_type,
                        1 if known_type else 0,
                        ledger_sequence,
                        sequence,
                        recorded_at,
                        now,
                        observe_event_json,
                    ),
                )
                conn.execute("COMMIT")
                return sequence
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def delete_project_events(self, project: str) -> int:
        """Used by rebuild: wipe one project's rows before a full rescan."""
        self.init_schema()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                cur = conn.execute("DELETE FROM observe_events WHERE project = ?", (project,))
                deleted = cur.rowcount
                conn.execute("DELETE FROM session_observation WHERE project = ?", (project,))
                conn.execute("COMMIT")
                return max(deleted, 0)
            except Exception:
                conn.execute("ROLLBACK")
                raise

    # --- canonical AgentSession mirror (H6) ---

    def upsert_session_observation(
        self,
        row: dict[str, Any],
        *,
        projection_sequence: int,
    ) -> None:
        self.init_schema()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                existing = conn.execute(
                    "SELECT last_projection_sequence FROM session_observation WHERE session_id = ?",
                    (row["session_id"],),
                ).fetchone()
                effective_sequence = projection_sequence
                if existing is not None:
                    effective_sequence = max(int(existing["last_projection_sequence"]), projection_sequence)
                conn.execute(
                    """
                    INSERT INTO session_observation (
                        session_id, project, repo, run_ids_json, subject_kind, subject_number,
                        command_kind, status, trace_id, correlation_id, risk_level, risk_tags_json,
                        invoked_by, acting_identity, created_at, updated_at, finished_at,
                        terminal_reason_code, terminal_reason_redacted, last_projection_sequence,
                        session_json
                    ) VALUES (
                        :session_id, :project, :repo, :run_ids_json, :subject_kind, :subject_number,
                        :command_kind, :status, :trace_id, :correlation_id, :risk_level, :risk_tags_json,
                        :invoked_by, :acting_identity, :created_at, :updated_at, :finished_at,
                        :terminal_reason_code, :terminal_reason_redacted, :last_projection_sequence,
                        :session_json
                    )
                    ON CONFLICT(session_id) DO UPDATE SET
                        project = excluded.project,
                        repo = excluded.repo,
                        run_ids_json = excluded.run_ids_json,
                        subject_kind = excluded.subject_kind,
                        subject_number = excluded.subject_number,
                        command_kind = excluded.command_kind,
                        status = excluded.status,
                        trace_id = excluded.trace_id,
                        correlation_id = excluded.correlation_id,
                        risk_level = excluded.risk_level,
                        risk_tags_json = excluded.risk_tags_json,
                        invoked_by = excluded.invoked_by,
                        acting_identity = excluded.acting_identity,
                        created_at = excluded.created_at,
                        updated_at = excluded.updated_at,
                        finished_at = excluded.finished_at,
                        terminal_reason_code = excluded.terminal_reason_code,
                        terminal_reason_redacted = excluded.terminal_reason_redacted,
                        last_projection_sequence = excluded.last_projection_sequence,
                        session_json = excluded.session_json
                    """,
                    {**row, "last_projection_sequence": effective_sequence},
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def get_session_observation(self, session_id: str) -> dict[str, Any] | None:
        self.init_schema()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM session_observation WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    # --- pagination helpers (library-level; no HTTP route in this ticket) ---

    def list_events_for_run(
        self,
        run_id: str,
        *,
        after_sequence: int = 0,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Keyset-paginated, ordered by the durable per-run projection_sequence."""
        self.init_schema()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM observe_events
                WHERE run_id = ? AND projection_sequence > ?
                ORDER BY projection_sequence ASC
                LIMIT ?
                """,
                (run_id, after_sequence, max(1, limit)),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_events_for_session(
        self,
        session_id: str,
        *,
        after_sequence: int = 0,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        self.init_schema()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM observe_events
                WHERE session_id = ? AND projection_sequence > ?
                ORDER BY projection_sequence ASC
                LIMIT ?
                """,
                (session_id, after_sequence, max(1, limit)),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_event_by_sequence(self, run_id: str, projection_sequence: int) -> dict[str, Any] | None:
        """Fetch exactly one row by its durable ``(run_id, projection_sequence)`` identity.

        Used by the protected SSE stream (V9 T03, H4 step 5) to fetch the
        authoritative row after a Redis ids-only notify -- the notify
        payload itself is never treated as display data, only as a signal
        to re-read this store.
        """
        self.init_schema()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM observe_events WHERE run_id = ? AND projection_sequence = ?",
                (run_id, projection_sequence),
            ).fetchone()
        return dict(row) if row is not None else None

    def get_project_for_run(self, run_id: str) -> str | None:
        """Canonical repo for *run_id* per the projected event rows (V9 T05).

        Used as a fallback when the run has no live session-index file (e.g.
        archived/pruned) but was already projected here -- callers must never
        derive the authorization-relevant repo from client input alone.
        """
        self.init_schema()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT project FROM observe_events WHERE run_id = ? LIMIT 1",
                (run_id,),
            ).fetchone()
        return row["project"] if row is not None else None

    def count_events_for_run(self, run_id: str) -> int:
        self.init_schema()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM observe_events WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return int(row["c"]) if row else 0

    # --- rebuild bookkeeping ---

    def set_watermark(
        self,
        *,
        project: str,
        last_ledger_sequence: int,
        events_projected: int,
        sessions_projected: int,
    ) -> None:
        self.init_schema()
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    """
                    INSERT INTO observe_watermark (
                        project, last_ledger_sequence, events_projected, sessions_projected, updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(project) DO UPDATE SET
                        last_ledger_sequence = excluded.last_ledger_sequence,
                        events_projected = excluded.events_projected,
                        sessions_projected = excluded.sessions_projected,
                        updated_at = excluded.updated_at
                    """,
                    (project, last_ledger_sequence, events_projected, sessions_projected, now),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def get_watermark(self, project: str) -> dict[str, Any] | None:
        self.init_schema()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM observe_watermark WHERE project = ?",
                (project,),
            ).fetchone()
        return dict(row) if row is not None else None
