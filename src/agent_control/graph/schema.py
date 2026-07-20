"""SQLite schema for graph-lite (Orbit 8a provenance columns)."""

from __future__ import annotations

DDL = """
CREATE TABLE IF NOT EXISTS repos (
    full_name TEXT PRIMARY KEY,
    snapshot_at TEXT NOT NULL,
    source_sha TEXT DEFAULT '',
    policy_source_sha TEXT DEFAULT '',
    extractor_version TEXT DEFAULT '',
    files_indexed INTEGER DEFAULT 0,
    files_skipped INTEGER DEFAULT 0,
    languages_supported TEXT DEFAULT 'python'
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
    confidence TEXT DEFAULT 'medium',
    provenance TEXT DEFAULT 'inferred',
    source_sha TEXT DEFAULT '',
    extractor_version TEXT DEFAULT '',
    last_verified_at TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_edges_repo ON edges(repo);
CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(repo, src_kind, src);
CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(repo, dst_kind, dst);
"""

# Columns added after Review MVP graph-lite — applied via migrate_schema().
_REPO_EXTRA_COLUMNS: tuple[tuple[str, str], ...] = (
    ("source_sha", "TEXT DEFAULT ''"),
    ("policy_source_sha", "TEXT DEFAULT ''"),
    ("extractor_version", "TEXT DEFAULT ''"),
    ("files_indexed", "INTEGER DEFAULT 0"),
    ("files_skipped", "INTEGER DEFAULT 0"),
    ("languages_supported", "TEXT DEFAULT 'python'"),
)

_EDGE_EXTRA_COLUMNS: tuple[tuple[str, str], ...] = (
    ("provenance", "TEXT DEFAULT 'inferred'"),
    ("source_sha", "TEXT DEFAULT ''"),
    ("extractor_version", "TEXT DEFAULT ''"),
    ("last_verified_at", "TEXT DEFAULT ''"),
)

_POST_MIGRATE_INDEXES: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_edges_kind ON edges(repo, kind)",
    "CREATE INDEX IF NOT EXISTS idx_edges_provenance ON edges(repo, provenance)",
)
