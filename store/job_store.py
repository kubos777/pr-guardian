"""Job Store — durable execution state and errors (SQLAlchemy).

This is the *only* source of truth for "what state is this review in".
The Celery broker (Redis) only needs to know "is there a task to run right
now"; if Redis is flushed, the Job Store still has the full history via
``job_events``. Keep it that way — never put durable state only in Celery.

The public API (dataclass ``Job``, dict-returning readers) is unchanged from
the previous SQLite implementation, so the webhook handler and the worker do
not need to know the backend is now SQLAlchemy (Postgres or SQLite).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from store import db
from store.db import Finding as FindingRow
from store.db import Job as JobRow
from store.db import JobEvent as JobEventRow
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


def _to_job(row: JobRow) -> Job:
    return Job(
        id=row.id,
        delivery_id=row.delivery_id,
        repository_id=row.repository_id,
        repo_full_name=row.repo_full_name,
        pr_number=row.pr_number,
        pr_title=row.pr_title,
        pr_author=row.pr_author,
        head_sha=row.head_sha,
        action=row.action,
        status=row.status,
        attempt_counts=json.loads(row.attempt_counts or "{}"),
        github_review_id=row.github_review_id,
        fingerprint_set_hash=row.fingerprint_set_hash,
        error=row.error,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _finding_to_dict(row: FindingRow) -> dict:
    return {
        "id": row.id,
        "job_id": row.job_id,
        "rule_id": row.rule_id,
        "severity": row.severity,
        "confidence": row.confidence,
        "path": row.path,
        "line": row.line,
        "side": row.side,
        "evidence": row.evidence,
        "message": row.message,
        "suggestion": row.suggestion,
        "historical_reference": row.historical_reference,
        "fingerprint": row.fingerprint,
        "github_comment_id": row.github_comment_id,
        "created_at": row.created_at,
    }


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
    with db.session() as s:
        existing = s.scalar(select(JobRow).where(JobRow.delivery_id == delivery_id))
        if existing is not None:
            return _to_job(existing), False, "duplicate_delivery"

        active = s.scalar(
            select(JobRow).where(
                JobRow.repository_id == repository_id,
                JobRow.pr_number == pr_number,
                JobRow.head_sha == head_sha,
                JobRow.status != Stage.FAILED.value,
            )
        )
        if active is not None:
            return _to_job(active), False, "duplicate_review"

        job = JobRow(
            delivery_id=delivery_id,
            repository_id=repository_id,
            repo_full_name=repo_full_name,
            pr_number=pr_number,
            pr_title=pr_title,
            pr_author=pr_author,
            head_sha=head_sha,
            action=action,
            status=Stage.RECEIVED.value,
        )
        s.add(job)
        try:
            s.flush()  # assign job.id, surface unique violations now
        except IntegrityError:
            s.rollback()
            row = s.scalar(select(JobRow).where(JobRow.delivery_id == delivery_id))
            if row is not None:
                return _to_job(row), False, "duplicate_delivery"
            row = s.scalar(
                select(JobRow).where(
                    JobRow.repository_id == repository_id,
                    JobRow.pr_number == pr_number,
                    JobRow.head_sha == head_sha,
                    JobRow.status != Stage.FAILED.value,
                )
            )
            if row is not None:
                return _to_job(row), False, "duplicate_review"
            raise

        s.add(
            JobEventRow(
                job_id=job.id,
                from_status=None,
                to_status=Stage.RECEIVED.value,
                message="Webhook signature verified; event accepted.",
            )
        )
        s.commit()
        return _to_job(job), True, "created"


def get_job(job_id: int) -> Optional[Job]:
    with db.session() as s:
        row = s.get(JobRow, job_id)
        return _to_job(row) if row else None


def get_latest_job() -> Optional[Job]:
    """Most recently created job, for the dashboard's GET /jobs/latest."""
    with db.session() as s:
        row = s.scalar(select(JobRow).order_by(JobRow.id.desc()).limit(1))
        return _to_job(row) if row else None


def transition(job_id: int, to_stage: Stage, message: str | None = None) -> Optional[Job]:
    """Move a job to a new stage and persist a job_event (requirement #11)."""
    with db.session() as s:
        row = s.get(JobRow, job_id)
        if row is None:
            return None
        from_status = row.status
        row.status = to_stage.value
        row.updated_at = db.utcnow_iso()
        s.add(
            JobEventRow(
                job_id=job_id,
                from_status=from_status,
                to_status=to_stage.value,
                message=message,
            )
        )
        s.commit()
        return _to_job(row)


def mark_failed(job_id: int, stage: Stage, error: str) -> Optional[Job]:
    detail = f"[{stage.value}] {error}"
    with db.session() as s:
        row = s.get(JobRow, job_id)
        if row is None:
            return None
        from_status = row.status
        row.status = Stage.FAILED.value
        row.error = detail
        row.updated_at = db.utcnow_iso()
        s.add(
            JobEventRow(
                job_id=job_id,
                from_status=from_status,
                to_status=Stage.FAILED.value,
                message=detail,
            )
        )
        s.commit()
        return _to_job(row)


def record_attempt(job_id: int, stage: Stage) -> int:
    """Increment and persist the attempt counter for a stage; returns the new count."""
    with db.session() as s:
        row = s.get(JobRow, job_id)
        counts = json.loads(row.attempt_counts or "{}")
        counts[stage.value] = counts.get(stage.value, 0) + 1
        row.attempt_counts = json.dumps(counts)
        s.commit()
        return counts[stage.value]


def get_job_events(job_id: int) -> list[dict]:
    with db.session() as s:
        rows = s.scalars(
            select(JobEventRow).where(JobEventRow.job_id == job_id).order_by(JobEventRow.id.asc())
        ).all()
        return [
            {
                "id": r.id,
                "job_id": r.job_id,
                "from_status": r.from_status,
                "to_status": r.to_status,
                "message": r.message,
                "created_at": r.created_at,
            }
            for r in rows
        ]


def save_findings(job_id: int, findings: list[dict]) -> list[dict]:
    """Persist validated findings (requirement #17), each with its fingerprint.

    Duplicate fingerprints are ignored (portable equivalent of the old
    ``INSERT OR IGNORE``) via a per-row savepoint.
    """
    saved = []
    with db.session() as s:
        for f in findings:
            row = FindingRow(
                job_id=job_id,
                rule_id=f["rule_id"],
                severity=f["severity"],
                confidence=f["confidence"],
                path=f["path"],
                line=f["line"],
                side=f.get("side", "RIGHT"),
                evidence=f.get("evidence"),
                message=f["message"],
                suggestion=f.get("suggestion"),
                historical_reference=(
                    json.dumps(f.get("historical_reference"))
                    if f.get("historical_reference")
                    else None
                ),
                fingerprint=f["fingerprint"],
            )
            try:
                with s.begin_nested():
                    s.add(row)
            except IntegrityError:
                # Duplicate fingerprint — already stored, skip silently.
                pass
            saved.append(f)
        s.commit()
    return saved


def get_findings(job_id: int) -> list[dict]:
    with db.session() as s:
        rows = s.scalars(select(FindingRow).where(FindingRow.job_id == job_id)).all()
        return [_finding_to_dict(r) for r in rows]


def mark_review_published(job_id: int, github_review_id: int, fingerprint_set_hash: str) -> Optional[Job]:
    with db.session() as s:
        row = s.get(JobRow, job_id)
        if row is None:
            return None
        from_status = row.status
        row.status = Stage.COMPLETED.value
        row.github_review_id = github_review_id
        row.fingerprint_set_hash = fingerprint_set_hash
        row.updated_at = db.utcnow_iso()
        s.add(
            JobEventRow(
                job_id=job_id,
                from_status=from_status,
                to_status=Stage.COMPLETED.value,
                message=f"Published github_review_id={github_review_id}",
            )
        )
        s.commit()
        return _to_job(row)


def find_completed_review(repository_id: int, pr_number: int, head_sha: str) -> Optional[Job]:
    """Requirement #15: look up a review already published for this exact sha."""
    with db.session() as s:
        row = s.scalar(
            select(JobRow).where(
                JobRow.repository_id == repository_id,
                JobRow.pr_number == pr_number,
                JobRow.head_sha == head_sha,
                JobRow.status == Stage.COMPLETED.value,
                JobRow.github_review_id.is_not(None),
            )
        )
        return _to_job(row) if row else None
