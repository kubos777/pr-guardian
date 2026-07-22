"""History Store — approved historical examples (SQLite, ``history_examples``).

Important: the MVP does **not** learn. Nothing in this module writes a row
automatically as a side effect of a review. Rows are added deliberately
(``add_approved_example``, e.g. from a human curation step or a fixture
loader for the demo) and later *retrieved* to give the LLM extra context
about how similar issues were fixed before. Everywhere else in the codebase
and docs this must be described as "retrieves approved historical
examples", never as the agent "learning".
"""

from __future__ import annotations

from store.db import get_connection


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
    conn = get_connection()
    with conn:
        cur = conn.execute(
            """
            INSERT INTO history_examples
                (repo_full_name, pr_number, rule_id, file_path, line, code_snippet, fix_description, approved_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (repo_full_name, pr_number, rule_id, file_path, line, code_snippet, fix_description, approved_by),
        )
    return cur.lastrowid


def get_related_examples(repo_full_name: str, file_paths: list[str], limit: int = 5) -> list[dict]:
    """Retrieve approved historical examples relevant to the changed files.

    Retrieval only — this never mutates state and is not a learning step.
    """
    conn = get_connection()
    if not file_paths:
        rows = conn.execute(
            "SELECT * FROM history_examples WHERE repo_full_name = ? ORDER BY created_at DESC LIMIT ?",
            (repo_full_name, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    placeholders = ",".join("?" for _ in file_paths)
    rows = conn.execute(
        f"""
        SELECT * FROM history_examples
        WHERE repo_full_name = ? AND file_path IN ({placeholders})
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (repo_full_name, *file_paths, limit),
    ).fetchall()
    return [dict(r) for r in rows]
