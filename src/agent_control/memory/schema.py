"""SQLite schema for trajectory memory."""

from __future__ import annotations

DDL = """
CREATE TABLE IF NOT EXISTS memory_records (
    run_id TEXT PRIMARY KEY,
    record_id TEXT NOT NULL UNIQUE,
    repo_owner TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    repo_full_name TEXT NOT NULL,
    issue_id INTEGER,
    pr_id INTEGER,
    source_command TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    record_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_memory_repo_issue
    ON memory_records(repo_full_name, issue_id, created_at DESC);

CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
    run_id UNINDEXED,
    repo_full_name UNINDEXED,
    content
);
"""
