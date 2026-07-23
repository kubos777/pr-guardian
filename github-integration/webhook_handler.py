"""PR Guardian - GitHub Webhook Handler (FastAPI).

Ingress only. This process's whole job is: verify the signature, decide
whether the event is in scope, deduplicate, persist a Job Store row,
enqueue the first pipeline stage, and answer with HTTP 202 — all before
any GitHub/LLM call happens. Everything past that point runs in the
Celery worker (see worker/tasks.py).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "github-integration"):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from store import db, job_store
from store.stages import Stage

ALLOWED_ACTIONS = {"opened", "synchronize"}

app = FastAPI(title="PR Guardian Webhook Handler")

logger = logging.getLogger(__name__)


@app.on_event("startup")
def _startup() -> None:
    db.init_db()


def _webhook_secret() -> str:
    secret = os.environ.get("GITHUB_WEBHOOK_SECRET")
    if not secret:
        raise RuntimeError("GITHUB_WEBHOOK_SECRET is not configured — refusing to accept webhooks")
    return secret


def verify_signature(raw_body: bytes, signature_header: str | None, secret: str) -> bool:
    """Requirement #1: validate X-Hub-Signature-256 before anything else."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def _enqueue_fetch_context(job_id: int) -> None:
    # Imported lazily so importing this module never requires Celery/Redis
    # to be reachable (e.g. for unit tests of signature validation alone).
    from worker.tasks import fetch_context_task

    job_store.transition(job_id, Stage.QUEUED, message="Enqueued for context fetch.")
    fetch_context_task.delay(job_id)


@app.post("/webhook")
async def webhook(request: Request) -> JSONResponse:
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")

    # Requirement #1: signature is validated BEFORE the body is parsed/used.
    if not verify_signature(raw_body, signature, _webhook_secret()):
        raise HTTPException(status_code=401, detail="invalid signature")

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="malformed JSON body")

    event = request.headers.get("X-GitHub-Event", "")
    delivery_id = request.headers.get("X-GitHub-Delivery", "")

    if event == "ping":
        return JSONResponse(status_code=200, content={"status": "pong"})

    if event != "pull_request":
        return JSONResponse(status_code=200, content={"status": "ignored", "reason": f"unsupported event: {event}"})

    action = payload.get("action")
    if action not in ALLOWED_ACTIONS:
        return JSONResponse(status_code=200, content={"status": "ignored", "reason": f"unsupported action: {action}"})

    if not delivery_id:
        raise HTTPException(status_code=400, detail="missing X-GitHub-Delivery header")

    repository = payload["repository"]
    pull_request = payload["pull_request"]

    job, created, reason = job_store.create_job(
        delivery_id=delivery_id,
        repository_id=repository["id"],
        repo_full_name=repository["full_name"],
        pr_number=pull_request["number"],
        pr_title=pull_request.get("title"),
        pr_author=(pull_request.get("user") or {}).get("login"),
        head_sha=pull_request["head"]["sha"],
        action=action,
    )

    if created:
        _enqueue_fetch_context(job.id)

    # Requirement #5: 202 immediately, whether this delivery created a new
    # job or was recognized as a duplicate of one already in flight.
    return JSONResponse(
        status_code=202,
        content={"job_id": job.id, "status": job.status, "dedup": reason},
    )


@app.get("/jobs/latest")
async def latest_job() -> JSONResponse:
    """Dashboard read model: the most recently received job plus whatever
    findings have been validated for it so far. ``job`` is null when no
    webhook delivery has ever created a job (fresh install / empty DB).
    """
    job = job_store.get_latest_job()
    if job is None:
        return JSONResponse(status_code=200, content={"job": None, "findings": []})

    findings = job_store.get_findings(job.id)
    return JSONResponse(
        status_code=200,
        content={
            "job": {
                "id": job.id,
                "repo_full_name": job.repo_full_name,
                "pr_number": job.pr_number,
                "pr_title": job.pr_title,
                "pr_author": job.pr_author,
                "status": job.status,
                "error": job.error,
                "updated_at": job.updated_at,
            },
            "findings": findings,
        },
    )


if __name__ == "__main__":
    import uvicorn

    db.init_db()
    uvicorn.run(
        app,
        host=os.environ.get("WEBHOOK_HOST", "0.0.0.0"),
        port=int(os.environ.get("WEBHOOK_PORT", "8000")),
    )
