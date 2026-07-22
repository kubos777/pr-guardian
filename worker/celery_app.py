"""Celery application (requirement #6: Celery + Redis as queue/broker).

Durable state lives in the SQLite Job Store, not in Celery/Redis — so
task results are ignored and ``acks_late`` + a prefetch of 1 make sure a
worker crash mid-task puts the job back on the queue instead of losing it
silently.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "agent-core", _REPO_ROOT / "github-integration"):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

from celery import Celery

BROKER_URL = os.environ.get("CELERY_BROKER_URL", os.environ.get("REDIS_URL", "redis://localhost:6379/0"))

celery_app = Celery("pr_guardian", broker=BROKER_URL, include=["worker.tasks"])

celery_app.conf.update(
    task_ignore_result=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_max_retries=int(os.environ.get("MAX_RETRY_ATTEMPTS", "3")),
)
