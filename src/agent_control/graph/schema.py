"""SQLite schema for graph-lite."""

from __future__ import annotations

DDL = """
CREATE TABLE IF NOT EXISTS repos (
    full_name TEXT PRIMARY KEY,
    snapshot_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo TEXT NOT NULL,
    path TEXT NOT NULL,
    UNIQUE(repo, path)
);

CREATE TABLE IF NOT EXISTS services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo TEXT NOT NULL,
    name TEXT NOT NULL,
    UNIQUE(repo, name)
);

CREATE TABLE IF NOT EXISTS tests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo TEXT NOT NULL,
    path TEXT NOT NULL,
    UNIQUE(repo, path)
);

CREATE TABLE IF NOT EXISTS adrs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo TEXT NOT NULL,
    adr_id TEXT NOT NULL,
    title TEXT,
    source_path TEXT,
    UNIQUE(repo, adr_id)
);

CREATE TABLE IF NOT EXISTS edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo TEXT NOT NULL,
    kind TEXT NOT NULL,
    src_kind TEXT NOT NULL,
    src TEXT NOT NULL,
    dst_kind TEXT NOT NULL,
    dst TEXT NOT NULL,
    confidence TEXT DEFAULT 'medium'
);

CREATE INDEX IF NOT EXISTS idx_edges_repo ON edges(repo);
CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(repo, src_kind, src);
CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(repo, dst_kind, dst);
"""
