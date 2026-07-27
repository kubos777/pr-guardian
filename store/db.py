"""Job Store persistence via SQLAlchemy (Postgres in prod, SQLite for tests).

The database is selected by ``DATABASE_URL``:
- Docker/production: ``postgresql://user:pass@host:5432/pr_guardian``
- Local dev (no DATABASE_URL): falls back to a SQLite file from
  ``PR_GUARDIAN_DB_PATH`` (default ``data/pr_guardian.db``).
- Tests: ``sqlite://`` (in-memory) via a StaticPool so the webhook thread
  and the eager Celery task share the same connection.

Four tables — ``jobs``, ``job_events``, ``findings``, ``history_examples`` —
are declared as ORM models. ``job_store``/``history_store`` convert these
ORM rows back into the plain dataclass / dict shapes the rest of the code
already expects, so the migration is invisible to the webhook handler and
the Celery worker.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
    BigInteger,
    Column,
    Float,
    Index,
    Integer,
    String,
    Text,
    create_engine,
    event,
    text,
)
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

_DB_PATH_ENV = "PR_GUARDIAN_DB_PATH"
_DEFAULT_DB_PATH = "data/pr_guardian.db"

Base = declarative_base()

_engine = None
_SessionLocal: sessionmaker | None = None


def utcnow_iso() -> str:
    """Timestamp string matching the previous SQLite format (ms + Z)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    delivery_id = Column(String, nullable=False, unique=True)
    # GitHub IDs are large — must be 64-bit (BigInteger) or Postgres INT4 overflows.
    repository_id = Column(BigInteger, nullable=False)
    repo_full_name = Column(String, nullable=False)
    pr_number = Column(Integer, nullable=False)
    pr_title = Column(String)
    pr_author = Column(String)
    head_sha = Column(String, nullable=False)
    action = Column(String, nullable=False)
    status = Column(String, nullable=False, default="RECEIVED")
    attempt_counts = Column(Text, nullable=False, default="{}")
    github_review_id = Column(BigInteger)
    fingerprint_set_hash = Column(String)
    error = Column(Text)
    created_at = Column(String, nullable=False, default=utcnow_iso)
    updated_at = Column(String, nullable=False, default=utcnow_iso, onupdate=utcnow_iso)

    # Requirement #4: only one non-FAILED job per (repo, PR, sha). A partial
    # unique index (both SQLite and Postgres support WHERE) enforces it so a
    # race between two deliveries can't create two active jobs.
    __table_args__ = (
        Index(
            "idx_jobs_active_review",
            "repository_id",
            "pr_number",
            "head_sha",
            unique=True,
            sqlite_where=text("status != 'FAILED'"),
            postgresql_where=text("status != 'FAILED'"),
        ),
    )


class JobEvent(Base):
    __tablename__ = "job_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, nullable=False, index=True)
    from_status = Column(String)
    to_status = Column(String, nullable=False)
    message = Column(Text)
    created_at = Column(String, nullable=False, default=utcnow_iso)


class Finding(Base):
    __tablename__ = "findings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, nullable=False, index=True)
    rule_id = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)
    path = Column(String, nullable=False)
    line = Column(Integer, nullable=False)
    side = Column(String, nullable=False, default="RIGHT")
    evidence = Column(Text)
    message = Column(Text, nullable=False)
    suggestion = Column(Text)
    historical_reference = Column(Text)
    fingerprint = Column(String, nullable=False, unique=True)
    github_comment_id = Column(BigInteger)
    created_at = Column(String, nullable=False, default=utcnow_iso)


class HistoryExample(Base):
    __tablename__ = "history_examples"

    id = Column(Integer, primary_key=True, autoincrement=True)
    repo_full_name = Column(String, nullable=False, index=True)
    pr_number = Column(Integer)
    rule_id = Column(String)
    file_path = Column(String)
    line = Column(Integer)
    code_snippet = Column(Text)
    fix_description = Column(Text)
    approved_by = Column(String)
    created_at = Column(String, nullable=False, default=utcnow_iso)


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    path = os.environ.get(_DB_PATH_ENV, _DEFAULT_DB_PATH)
    return f"sqlite:///{path}"


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def _is_memory(url: str) -> bool:
    return url in ("sqlite://", "sqlite:///:memory:")


def get_engine():
    global _engine, _SessionLocal
    if _engine is not None:
        return _engine

    url = _database_url()
    kwargs: dict = {"future": True}

    if _is_sqlite(url):
        kwargs["connect_args"] = {"check_same_thread": False}
        if _is_memory(url):
            # Share one connection across threads so the webhook thread and
            # the eager Celery task see the same in-memory DB.
            kwargs["poolclass"] = StaticPool
        else:
            # Ensure the parent dir exists for file-based SQLite.
            db_file = url.replace("sqlite:///", "", 1)
            Path(db_file).parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(url, **kwargs)

    if _is_sqlite(url):

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL;")
            cur.execute("PRAGMA foreign_keys=ON;")
            cur.close()

    _engine = engine
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


def session() -> Session:
    """Return a new SQLAlchemy session (caller is responsible for closing)."""
    if _SessionLocal is None:
        get_engine()
    assert _SessionLocal is not None
    return _SessionLocal()


def init_db() -> str:
    """Idempotently create all tables. Safe to call at process startup."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    return _database_url()


def reset_engine() -> None:
    """Dispose the engine so the next init_db() re-reads DATABASE_URL /
    PR_GUARDIAN_DB_PATH. Used by the test suite between cases."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


if __name__ == "__main__":
    url = init_db()
    print(f"Job Store schema ready at {url}")
