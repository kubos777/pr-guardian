"""Job Store — durable execution state and errors (SQLite).

This is the *only* source of truth for "what state is this review in".
The Celery broker (Redis) only needs to know "is there a task to run right
now"; if Redis is flushed, the Job Store still has the full history via
``job_events``. Keep it that way — never put durable state only in Celery.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Optional

from store.db import get_connection
from store.stages import Stage


@dataclass
class Job:
    id: int
    delivery_id: str
    repository_id: int
    repo_full_name: str
    pr_number: int
    pr_title: Optional[str]
    pr_author: Optional[str]
    head_sha: str
    action: str
    status: str
    attempt_counts: dict
    github_review_id: Optional[int]
    fingerprint_set_hash: Optional[str]
    error: Optional[str]
    created_at: str
    updated_at: str

    @property
    def stage(self) -> Stage:
        return Stage(self.status)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Job":
        data = dict(row)
        data["attempt_counts"] = json.loads(data["attempt_counts"] or "{}")
        return cls(**data)


def _fetch_by_delivery_id(conn: sqlite3.Connection, delivery_id: str) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM jobs WHERE delivery_id = ?", (delivery_id,)).fetchone()


def _fetch_active_review(
    conn: sqlite3.Connection, repository_id: int, pr_number: int, head_sha: str
) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM jobs WHERE repository_id = ? AND pr_number = ? AND head_sha = ? "
        "AND status != 'FAILED'",
        (repository_id, pr_number, head_sha),
    ).fetchone()


def create_job(
    *,
    delivery_id: str,
    repository_id: int,
    repo_full_name: str,
    pr_number: int,
    head_sha: str,
    action: str,
    pr_title: Optional[str] = None,
    pr_author: Optional[str] = None,
) -> tuple[Job, bool, str]:
    """Create a job, enforcing both dedupe layers (requirements #3 and #4).

    Returns (job, created, reason). ``reason`` is one of
    "created", "duplicate_delivery", "duplicate_review".
    """
    conn = get_connection()

    existing = _fetch_by_delivery_id(conn, delivery_id)
    if existing is not None:
        return Job.from_row(existing), False, "duplicate_delivery"

    existing_review = _fetch_active_review(conn, repository_id, pr_number, head_sha)
    if existing_review is not None:
        return Job.from_row(existing_review), False, "duplicate_review"

    try:
        with conn:
            cur = conn.execute(
                """
                INSERT INTO jobs
                    (delivery_id, repository_id, repo_full_name, pr_number, pr_title, pr_author,
                     head_sha, action, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    delivery_id,
                    repository_id,
                    repo_full_name,
                    pr_number,
                    pr_title,
                    pr_author,
                    head_sha,
                    action,
                    Stage.RECEIVED.value,
                ),
            )
            job_id = cur.lastrowid
            conn.execute(
                "INSERT INTO job_events (job_id, from_status, to_status, message) VALUES (?, NULL, ?, ?)",
                (job_id, Stage.RECEIVED.value, "Webhook signature verified; event accepted."),
            )
    except sqlite3.IntegrityError:
        # Lost a race against a concurrent request for the same delivery/review.
        row = _fetch_by_delivery_id(conn, delivery_id)
        if row is not None:
            return Job.from_row(row), False, "duplicate_delivery"
        row = _fetch_active_review(conn, repository_id, pr_number, head_sha)
        if row is not None:
            return Job.from_row(row), False, "duplicate_review"
        raise

    return get_job(job_id), True, "created"


def get_job(job_id: int) -> Optional[Job]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return Job.from_row(row) if row else None


def get_latest_job() -> Optional[Job]:
    """Most recently created job, for the dashboard's GET /jobs/latest."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT 1").fetchone()
    return Job.from_row(row) if row else None


def transition(job_id: int, to_stage: Stage, message: str | None = None) -> Job:
    """Move a job to a new stage and persist a job_event (requirement #11)."""
    conn = get_connection()
    with conn:
        current = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
        from_status = current["status"] if current else None
        conn.execute(
            "UPDATE jobs SET status = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ?",
            (to_stage.value, job_id),
        )
        conn.execute(
            "INSERT INTO job_events (job_id, from_status, to_status, message) VALUES (?, ?, ?, ?)",
            (job_id, from_status, to_stage.value, message),
        )
    return get_job(job_id)


def mark_failed(job_id: int, stage: Stage, error: str) -> Job:
    conn = get_connection()
    with conn:
        current = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
        from_status = current["status"] if current else None
        conn.execute(
            "UPDATE jobs SET status = ?, error = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') "
            "WHERE id = ?",
            (Stage.FAILED.value, f"[{stage.value}] {error}", job_id),
        )
        conn.execute(
            "INSERT INTO job_events (job_id, from_status, to_status, message) VALUES (?, ?, ?, ?)",
            (job_id, from_status, Stage.FAILED.value, f"[{stage.value}] {error}"),
        )
    return get_job(job_id)


def record_attempt(job_id: int, stage: Stage) -> int:
    """Increment and persist the attempt counter for a stage; returns the new count."""
    conn = get_connection()
    with conn:
        row = conn.execute("SELECT attempt_counts FROM jobs WHERE id = ?", (job_id,)).fetchone()
        counts = json.loads(row["attempt_counts"] or "{}")
        counts[stage.value] = counts.get(stage.value, 0) + 1
        conn.execute(
            "UPDATE jobs SET attempt_counts = ? WHERE id = ?",
            (json.dumps(counts), job_id),
        )
    return counts[stage.value]


def get_job_events(job_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM job_events WHERE job_id = ? ORDER BY id ASC", (job_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def save_findings(job_id: int, findings: list[dict]) -> list[dict]:
    """Persist validated findings (requirement #17), each with its fingerprint."""
    conn = get_connection()
    saved = []
    with conn:
        for f in findings:
            conn.execute(
                """
                INSERT OR IGNORE INTO findings
                    (job_id, rule_id, severity, confidence, path, line, side,
                     evidence, message, suggestion, historical_reference, fingerprint)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    f["rule_id"],
                    f["severity"],
                    f["confidence"],
                    f["path"],
                    f["line"],
                    f.get("side", "RIGHT"),
                    f.get("evidence"),
                    f["message"],
                    f.get("suggestion"),
                    json.dumps(f.get("historical_reference")) if f.get("historical_reference") else None,
                    f["fingerprint"],
                ),
            )
            saved.append(f)
    return saved


def get_findings(job_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM findings WHERE job_id = ?", (job_id,)).fetchall()
    return [dict(r) for r in rows]


def mark_review_published(job_id: int, github_review_id: int, fingerprint_set_hash: str) -> Job:
    conn = get_connection()
    with conn:
        current = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
        from_status = current["status"] if current else None
        conn.execute(
            "UPDATE jobs SET status = ?, github_review_id = ?, fingerprint_set_hash = ?, "
            "updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ?",
            (Stage.COMPLETED.value, github_review_id, fingerprint_set_hash, job_id),
        )
        conn.execute(
            "INSERT INTO job_events (job_id, from_status, to_status, message) VALUES (?, ?, ?, ?)",
            (job_id, from_status, Stage.COMPLETED.value, f"Published github_review_id={github_review_id}"),
        )
    return get_job(job_id)


def find_completed_review(repository_id: int, pr_number: int, head_sha: str) -> Optional[Job]:
    """Requirement #15: look up a review already published for this exact sha."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM jobs WHERE repository_id = ? AND pr_number = ? AND head_sha = ? "
        "AND status = 'COMPLETED' AND github_review_id IS NOT NULL",
        (repository_id, pr_number, head_sha),
    ).fetchone()
    return Job.from_row(row) if row else None
