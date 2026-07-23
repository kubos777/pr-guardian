"""Shared Celery Task base class: on terminal failure, persist FAILED to
the Job Store. This fires exactly once per job — either immediately (a
``NonRetryableError``, first attempt) or after Celery's autoretry has
exhausted ``max_retries`` attempts of a ``RetryableError`` (requirement
#12/#13). Either way the Job Store — not Celery/Redis — ends up holding
the terminal state and the error message (requirement #11).
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "agent-core", _REPO_ROOT / "github-integration"):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

from celery import Task

from store import job_store
from store.stages import Stage


class StageTask(Task):
    abstract = True
    stage: Stage = None

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        job_id = args[0] if args else kwargs.get("job_id")
        if job_id is None:
            return
        job_store.mark_failed(job_id, stage=self.stage, error=f"{type(exc).__name__}: {exc}")
