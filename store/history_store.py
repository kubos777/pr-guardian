"""History Store — approved historical examples (SQLAlchemy, ``history_examples``).

Important: the MVP does **not** learn. Nothing in this module writes a row
automatically as a side effect of a review. Rows are added deliberately
(``add_approved_example``, e.g. from a human curation step or a fixture
loader for the demo) and later *retrieved* to give the LLM extra context
about how similar issues were fixed before. Everywhere else in the codebase
and docs this must be described as "retrieves approved historical
examples", never as the agent "learning".
"""

from __future__ import annotations

from sqlalchemy import select

from store import db
from store.db import HistoryExample


def _to_dict(row: HistoryExample) -> dict:
    return {
        "id": row.id,
        "repo_full_name": row.repo_full_name,
        "pr_number": row.pr_number,
        "rule_id": row.rule_id,
        "file_path": row.file_path,
        "line": row.line,
        "code_snippet": row.code_snippet,
        "fix_description": row.fix_description,
        "approved_by": row.approved_by,
        "created_at": row.created_at,
    }


def add_approved_example(
    *,
    repo_full_name: str,
    rule_id: str,
    file_path: str,
    line: int,
    code_snippet: str,
    fix_description: str,
    approved_by: str,
    pr_number: int | None = None,
) -> int:
    with db.session() as s:
        row = HistoryExample(
            repo_full_name=repo_full_name,
            pr_number=pr_number,
            rule_id=rule_id,
            file_path=file_path,
            line=line,
            code_snippet=code_snippet,
            fix_description=fix_description,
            approved_by=approved_by,
        )
        s.add(row)
        s.commit()
        return row.id


def get_related_examples(repo_full_name: str, file_paths: list[str], limit: int = 5) -> list[dict]:
    """Retrieve approved historical examples relevant to the changed files.

    Retrieval only — this never mutates state and is not a learning step.
    """
    with db.session() as s:
        stmt = select(HistoryExample).where(HistoryExample.repo_full_name == repo_full_name)
        if file_paths:
            stmt = stmt.where(HistoryExample.file_path.in_(file_paths))
        stmt = stmt.order_by(HistoryExample.created_at.desc()).limit(limit)
        rows = s.scalars(stmt).all()
        return [_to_dict(r) for r in rows]
