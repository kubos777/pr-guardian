"""PR Guardian - persistence layer.

Three conceptually separate stores share this package, but they are NOT the
same thing and must not be conflated:

- ``job_store``: the durable **Job Store** (SQLite, ``data/pr_guardian.db``).
  Execution state, stage transitions and errors. Source of truth for "what
  happened to this review".
- ``context_cache``: the ephemeral **Context Cache** (Redis, TTL-based).
  Short-lived GitHub API / repo-config responses. Safe to lose; never a
  source of truth.
- ``history_store``: the **History Store** (SQLite, ``history_examples``
  table). Human-approved past findings retrieved for extra context. The
  MVP *retrieves approved historical examples* — it does not learn or
  update itself automatically.
"""
