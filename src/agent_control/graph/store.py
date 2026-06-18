"""SQLite graph store."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from agent_control.graph.schema import DDL


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
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO repos(full_name, snapshot_at) VALUES (?, ?) "
                "ON CONFLICT(full_name) DO UPDATE SET snapshot_at = excluded.snapshot_at",
                (repo, now),
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
                "INSERT INTO edges(repo, kind, src_kind, src, dst_kind, dst, confidence) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        repo,
                        e["kind"],
                        e["src_kind"],
                        e["src"],
                        e["dst_kind"],
                        e["dst"],
                        e.get("confidence", "medium"),
                    )
                    for e in edges
                ],
            )

    def has_repo(self, repo: str) -> bool:
        self.init_schema()
        with self.connect() as conn:
            row = conn.execute("SELECT 1 FROM repos WHERE full_name = ?", (repo,)).fetchone()
            return row is not None

    def list_edges(self, repo: str | None = None) -> list[dict[str, Any]]:
        self.init_schema()
        with self.connect() as conn:
            if repo:
                rows = conn.execute("SELECT * FROM edges WHERE repo = ?", (repo,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM edges").fetchall()
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
