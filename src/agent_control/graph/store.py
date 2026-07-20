"""SQLite graph store with Orbit provenance fields."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from agent_control.graph.provenance import EXTRACTOR_VERSION, normalize_provenance
from agent_control.graph.schema import (
    DDL,
    _EDGE_EXTRA_COLUMNS,
    _POST_MIGRATE_INDEXES,
    _REPO_EXTRA_COLUMNS,
)


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(r[1]) for r in rows}


def migrate_schema(conn: sqlite3.Connection) -> None:
    """Add Orbit columns to existing graph-lite DBs without wiping data."""
    repo_cols = _table_columns(conn, "repos")
    for name, decl in _REPO_EXTRA_COLUMNS:
        if name not in repo_cols:
            conn.execute(f"ALTER TABLE repos ADD COLUMN {name} {decl}")

    edge_cols = _table_columns(conn, "edges")
    for name, decl in _EDGE_EXTRA_COLUMNS:
        if name not in edge_cols:
            conn.execute(f"ALTER TABLE edges ADD COLUMN {name} {decl}")

    for stmt in _POST_MIGRATE_INDEXES:
        conn.execute(stmt)


class GraphStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(DDL)
            migrate_schema(conn)

    def clear_repo(self, repo: str) -> None:
        with self.connect() as conn:
            for table in ("files", "services", "tests", "adrs", "edges"):
                conn.execute(f"DELETE FROM {table} WHERE repo = ?", (repo,))
            conn.execute("DELETE FROM repos WHERE full_name = ?", (repo,))

    def upsert_snapshot(
        self,
        repo: str,
        *,
        files: list[str],
        services: list[str],
        tests: list[str],
        adrs: list[dict[str, str]],
        edges: list[dict[str, str]],
        source_sha: str = "",
        policy_source_sha: str = "",
        extractor_version: str = EXTRACTOR_VERSION,
        files_indexed: int | None = None,
        files_skipped: int = 0,
        languages_supported: str = "python",
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        indexed = len(files) if files_indexed is None else files_indexed
        with self.connect() as conn:
            migrate_schema(conn)
            conn.execute(
                "INSERT INTO repos("
                "full_name, snapshot_at, source_sha, policy_source_sha, "
                "extractor_version, files_indexed, files_skipped, languages_supported"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(full_name) DO UPDATE SET "
                "snapshot_at = excluded.snapshot_at, "
                "source_sha = excluded.source_sha, "
                "policy_source_sha = excluded.policy_source_sha, "
                "extractor_version = excluded.extractor_version, "
                "files_indexed = excluded.files_indexed, "
                "files_skipped = excluded.files_skipped, "
                "languages_supported = excluded.languages_supported",
                (
                    repo,
                    now,
                    source_sha,
                    policy_source_sha,
                    extractor_version,
                    indexed,
                    files_skipped,
                    languages_supported,
                ),
            )
            conn.execute("DELETE FROM files WHERE repo = ?", (repo,))
            conn.execute("DELETE FROM services WHERE repo = ?", (repo,))
            conn.execute("DELETE FROM tests WHERE repo = ?", (repo,))
            conn.execute("DELETE FROM adrs WHERE repo = ?", (repo,))
            conn.execute("DELETE FROM edges WHERE repo = ?", (repo,))

            conn.executemany(
                "INSERT INTO files(repo, path) VALUES (?, ?)",
                [(repo, p) for p in files],
            )
            conn.executemany(
                "INSERT INTO services(repo, name) VALUES (?, ?)",
                [(repo, s) for s in services],
            )
            conn.executemany(
                "INSERT INTO tests(repo, path) VALUES (?, ?)",
                [(repo, t) for t in tests],
            )
            conn.executemany(
                "INSERT INTO adrs(repo, adr_id, title, source_path) VALUES (?, ?, ?, ?)",
                [(repo, a["adr_id"], a.get("title", ""), a.get("source_path", "")) for a in adrs],
            )
            conn.executemany(
                "INSERT INTO edges("
                "repo, kind, src_kind, src, dst_kind, dst, confidence, "
                "provenance, source_sha, extractor_version, last_verified_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        repo,
                        e["kind"],
                        e["src_kind"],
                        e["src"],
                        e["dst_kind"],
                        e["dst"],
                        e.get("confidence", "medium"),
                        normalize_provenance(e.get("provenance")),
                        e.get("source_sha") or source_sha,
                        e.get("extractor_version") or extractor_version,
                        e.get("last_verified_at") or now,
                    )
                    for e in edges
                ],
            )

    def has_repo(self, repo: str) -> bool:
        self.init_schema()
        with self.connect() as conn:
            row = conn.execute("SELECT 1 FROM repos WHERE full_name = ?", (repo,)).fetchone()
            return row is not None

    def repo_meta(self, repo: str) -> dict[str, Any] | None:
        self.init_schema()
        with self.connect() as conn:
            migrate_schema(conn)
            row = conn.execute("SELECT * FROM repos WHERE full_name = ?", (repo,)).fetchone()
            return dict(row) if row else None

    def list_edges(
        self,
        repo: str | None = None,
        *,
        kind: str | None = None,
        provenance: str | None = None,
    ) -> list[dict[str, Any]]:
        self.init_schema()
        clauses: list[str] = []
        params: list[Any] = []
        if repo:
            clauses.append("repo = ?")
            params.append(repo)
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if provenance:
            clauses.append("provenance = ?")
            params.append(provenance)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as conn:
            migrate_schema(conn)
            rows = conn.execute(f"SELECT * FROM edges {where}", params).fetchall()
            return [dict(r) for r in rows]

    def summary(self) -> dict[str, int]:
        with self.connect() as conn:
            counts: dict[str, int] = {}
            for table in ("repos", "files", "services", "tests", "adrs", "edges"):
                row = conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()
                counts[table] = int(row["c"]) if row else 0
            return counts

    def services_for_repo(self, repo: str) -> list[str]:
        self.init_schema()
        with self.connect() as conn:
            rows = conn.execute("SELECT name FROM services WHERE repo = ?", (repo,)).fetchall()
            return [r["name"] for r in rows]

    def tests_for_repo(self, repo: str) -> list[str]:
        self.init_schema()
        with self.connect() as conn:
            rows = conn.execute("SELECT path FROM tests WHERE repo = ?", (repo,)).fetchall()
            return [r["path"] for r in rows]

    def adrs_for_repo(self, repo: str) -> list[str]:
        self.init_schema()
        with self.connect() as conn:
            rows = conn.execute("SELECT adr_id FROM adrs WHERE repo = ?", (repo,)).fetchall()
            return [r["adr_id"] for r in rows]
