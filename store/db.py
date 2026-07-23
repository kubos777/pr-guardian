"""SQLite Job Store connection + schema.

A single file (``data/pr_guardian.db``, path from ``PR_GUARDIAN_DB_PATH``)
holds four tables: ``jobs``, ``job_events``, ``findings`` and
``history_examples``. WAL mode is enabled so the webhook process and the
Celery worker process can read/write concurrently without locking each
other out — that's why ``data/*.db-wal`` and ``data/*.db-shm`` exist next
to the main file and are gitignored alongside it.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path

_DB_PATH_ENV = "PR_GUARDIAN_DB_PATH"
_DEFAULT_DB_PATH = "data/pr_guardian.db"

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    delivery_id         TEXT NOT NULL UNIQUE,
    repository_id       INTEGER NOT NULL,
    repo_full_name      TEXT NOT NULL,
    pr_number           INTEGER NOT NULL,
    head_sha            TEXT NOT NULL,
    action              TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'RECEIVED',
    attempt_counts      TEXT NOT NULL DEFAULT '{}',
    github_review_id    INTEGER,
    fingerprint_set_hash TEXT,
    error               TEXT,
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Requirement #4: dedupe reviews by repository_id + pr_number + head_sha.
-- Only one non-FAILED job may be active for a given (repo, PR, sha) triple;
-- a FAILED job does not block a fresh retry job for the same sha.
CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_active_review
    ON jobs (repository_id, pr_number, head_sha)
    WHERE status != 'FAILED';

CREATE TABLE IF NOT EXISTS job_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      INTEGER NOT NULL REFERENCES jobs(id),
    from_status TEXT,
    to_status   TEXT NOT NULL,
    message     TEXT,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_job_events_job_id ON job_events (job_id);

CREATE TABLE IF NOT EXISTS findings (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id                INTEGER NOT NULL REFERENCES jobs(id),
    rule_id               TEXT NOT NULL,
    severity              TEXT NOT NULL,
    confidence            REAL NOT NULL,
    path                  TEXT NOT NULL,
    line                  INTEGER NOT NULL,
    side                  TEXT NOT NULL DEFAULT 'RIGHT',
    evidence              TEXT,
    message               TEXT NOT NULL,
    suggestion            TEXT,
    historical_reference  TEXT,
    fingerprint           TEXT NOT NULL UNIQUE,
    github_comment_id     INTEGER,
    created_at            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_findings_job_id ON findings (job_id);

-- History Store: human-approved past examples, retrieved (never
-- auto-learned) to enrich review context. See store/history_store.py.
CREATE TABLE IF NOT EXISTS history_examples (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_full_name  TEXT NOT NULL,
    pr_number       INTEGER,
    rule_id         TEXT,
    file_path       TEXT,
    line            INTEGER,
    code_snippet    TEXT,
    fix_description TEXT,
    approved_by     TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_history_examples_repo ON history_examples (repo_full_name);
"""


def db_path() -> Path:
    return Path(os.environ.get(_DB_PATH_ENV, _DEFAULT_DB_PATH))


def _init_connection(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.executescript(SCHEMA)
    conn.commit()


def get_connection() -> sqlite3.Connection:
    """Return a thread-local, schema-initialized SQLite connection."""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        return conn

    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    _init_connection(conn)
    _local.conn = conn
    return conn


def init_db() -> Path:
    """Idempotently create the schema. Safe to call at process startup."""
    get_connection()
    return db_path()


if __name__ == "__main__":
    p = init_db()
    print(f"Job Store schema ready at {p.resolve()}")
