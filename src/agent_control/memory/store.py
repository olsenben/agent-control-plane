"""SQLite memory store (CT103 sole writer)."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from agent_control.memory.schema import DDL
from agent_shared.models.memory import MemoryRecord


class MemoryStore:
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

    def upsert_record(self, record: MemoryRecord) -> MemoryRecord:
        self.init_schema()
        payload = record.model_copy(update={"review_result": None, "plan_result": None}).model_dump(
            mode="json"
        )
        fts_text = _fts_content(record)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO memory_records (
                    run_id, record_id, repo_owner, repo_name, repo_full_name,
                    issue_id, pr_id, source_command, created_at, updated_at, record_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    record_id = excluded.record_id,
                    repo_owner = excluded.repo_owner,
                    repo_name = excluded.repo_name,
                    repo_full_name = excluded.repo_full_name,
                    issue_id = excluded.issue_id,
                    pr_id = excluded.pr_id,
                    source_command = excluded.source_command,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    record_json = excluded.record_json
                """,
                (
                    record.run_id,
                    record.record_id,
                    record.repo_owner,
                    record.repo_name,
                    record.repo_full_name,
                    record.issue_id,
                    record.pr_id,
                    record.source_command,
                    record.created_at,
                    record.updated_at,
                    json.dumps(payload),
                ),
            )
            conn.execute("DELETE FROM memory_fts WHERE run_id = ?", (record.run_id,))
            conn.execute(
                "INSERT INTO memory_fts(run_id, repo_full_name, content) VALUES (?, ?, ?)",
                (record.run_id, record.repo_full_name, fts_text),
            )
        return record

    def get_by_run_id(self, run_id: str) -> MemoryRecord | None:
        self.init_schema()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT record_json FROM memory_records WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return MemoryRecord.model_validate(json.loads(row["record_json"]))

    def get_latest(self, repo_full_name: str, issue_id: int) -> MemoryRecord | None:
        self.init_schema()
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT record_json FROM memory_records
                WHERE repo_full_name = ? AND issue_id = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (repo_full_name, issue_id),
            ).fetchone()
        if row is None:
            return None
        return MemoryRecord.model_validate(json.loads(row["record_json"]))

    def list_for_issue(
        self,
        repo_full_name: str,
        issue_id: int,
        *,
        limit: int = 10,
    ) -> list[MemoryRecord]:
        self.init_schema()
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT record_json FROM memory_records
                WHERE repo_full_name = ? AND issue_id = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (repo_full_name, issue_id, limit),
            ).fetchall()
        return [MemoryRecord.model_validate(json.loads(r["record_json"])) for r in rows]

    def summary(self) -> dict[str, int]:
        self.init_schema()
        with self.connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM memory_records").fetchone()
            return {"memory_records": int(row["c"]) if row else 0}


def _fts_content(record: MemoryRecord) -> str:
    parts: list[str] = [
        record.source_command,
        record.confidence,
        record.suspected_root_cause or "",
    ]
    for finding in record.findings:
        parts.append(finding.summary)
    if record.recommended_next_step:
        parts.append(record.recommended_next_step.rationale)
    return "\n".join(p for p in parts if p)
