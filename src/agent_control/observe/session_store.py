"""Server-side OAuth `state` + login session store for the Observatory (V9 T05).

Two durable, short-lived tables in a dedicated ``observe_sessions.sqlite``
(separate file from the ``observe_event.v1`` projection store in
:mod:`agent_control.observe.store` -- different lifecycle, different
retention, no reason to share a schema):

``observe_oauth_state``
    One row per issued OAuth ``state`` nonce. Single-use (``consume_state``
    marks it used and refuses a second consume) and short-TTL
    (``OBSERVE_OAUTH_STATE_TTL_SECONDS``, default 10 minutes). Binding the
    callback to a value that is both (a) recorded server-side and (b) echoed
    back in an HttpOnly cookie the browser presents is the anti-CSRF /
    anti-replay defense for the login flow.

``observe_session``
    One row per authenticated Observatory session. ``session_id`` is always
    freshly minted with :func:`secrets.token_urlsafe` *after* a successful
    Gitea code exchange -- never accepted from client input at any stage --
    which is the session-fixation defense this ticket requires: an attacker
    cannot pre-seed a victim's session identifier because the identifier a
    client ends up holding is one the server generated post-authentication,
    not one that existed (or was guessable) beforehand.

Same connection pattern as :class:`agent_control.observe.store.ObserveStore`
(WAL journal mode, generous ``busy_timeout``, explicit ``BEGIN IMMEDIATE``
transactions) -- single-writer CT103 homelab scale.
"""

from __future__ import annotations

import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

BUSY_TIMEOUT_MS = 5000

DEFAULT_SESSION_TTL_SECONDS = 43200  # 12h, mirrors Settings.observe_session_ttl_seconds default
DEFAULT_STATE_TTL_SECONDS = 600  # 10m, mirrors Settings.observe_oauth_state_ttl_seconds default

DDL = """
CREATE TABLE IF NOT EXISTS observe_oauth_state (
    state TEXT PRIMARY KEY,
    next_path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS observe_session (
    session_id TEXT PRIMARY KEY,
    gitea_login TEXT NOT NULL,
    gitea_user_id INTEGER,
    access_token TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);
"""


def observe_sessions_db_path(state_root: Path) -> Path:
    """Default observe_sessions.sqlite location under agent_state_root."""
    return state_root / "observe" / "observe_sessions.sqlite"


class ObserveSessionStore:
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

    # --- OAuth state: CSRF + anti session-fixation binding ---

    def create_state(self, next_path: str, *, ttl_seconds: int = DEFAULT_STATE_TTL_SECONDS) -> str:
        self.init_schema()
        state = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=max(1, ttl_seconds))
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO observe_oauth_state (state, next_path, created_at, expires_at, used) "
                "VALUES (?, ?, ?, ?, 0)",
                (state, next_path, now.isoformat(), expires.isoformat()),
            )
        return state

    def consume_state(self, state: str) -> str | None:
        """Validate + single-use consume a `state` value.

        Returns the originally requested ``next_path`` on success, or ``None``
        when the state is unknown, already used (replay), or expired. Marking
        it used happens in the same transaction as the validity check so a
        state value can never be consumed twice, even under concurrent
        callback requests for the same value.
        """
        self.init_schema()
        if not state:
            return None
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT next_path, expires_at, used FROM observe_oauth_state WHERE state = ?",
                    (state,),
                ).fetchone()
                if row is None or row["used"] or row["expires_at"] < now:
                    conn.execute("COMMIT")
                    return None
                conn.execute("UPDATE observe_oauth_state SET used = 1 WHERE state = ?", (state,))
                conn.execute("COMMIT")
                return row["next_path"]
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def purge_expired_state(self) -> int:
        """Best-effort cleanup; not required for correctness (consume already checks TTL)."""
        self.init_schema()
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM observe_oauth_state WHERE expires_at < ?", (now,))
            return max(cur.rowcount, 0)

    # --- Sessions: fresh identifier minted only post-authentication ---

    def create_session(
        self,
        *,
        gitea_login: str,
        gitea_user_id: int | None,
        access_token: str,
        ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS,
    ) -> str:
        self.init_schema()
        session_id = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=max(1, ttl_seconds))
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO observe_session (
                    session_id, gitea_login, gitea_user_id, access_token,
                    created_at, expires_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    gitea_login,
                    gitea_user_id,
                    access_token,
                    now.isoformat(),
                    expires.isoformat(),
                    now.isoformat(),
                ),
            )
        return session_id

    def get_session(self, session_id: str | None) -> dict[str, Any] | None:
        if not session_id:
            return None
        self.init_schema()
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM observe_session WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        if row["expires_at"] < now:
            # Expired: eagerly drop it rather than leaving a stale row that a
            # future guess/replay of the same id could otherwise resurrect.
            self.delete_session(session_id)
            return None
        return dict(row)

    def delete_session(self, session_id: str | None) -> None:
        if not session_id:
            return
        self.init_schema()
        with self._connect() as conn:
            conn.execute("DELETE FROM observe_session WHERE session_id = ?", (session_id,))
