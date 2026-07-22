"""Celery pipeline: FETCHING_CONTEXT -> ANALYZING -> VALIDATING ->
POSTING_TO_GITHUB -> COMPLETED (or FAILED from any stage).

Each stage is its own Celery task, chained via ``.delay()`` on success.
That is what makes "retry the failed stage only" (requirement #12) true:
a retry of ``publish_task`` re-reads persisted findings/context, it never
re-runs ``analyze_task``. Only FETCHING_CONTEXT, ANALYZING and
POSTING_TO_GITHUB carry a retry policy (``autoretry_for=(RetryableError,)``
with backoff+jitter, max 3 attempts); VALIDATING is deterministic
(Pydantic + diff cross-check) and fails straight to FAILED, matching
requirement #12's "do not retry deterministic validation failures".
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "agent-core", _REPO_ROOT / "github-integration"):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

from pydantic import ValidationError

import main as agent_core_main
from diff_utils import DiffIndex
from exceptions import LLMFatalError, LLMTransientError
from fingerprint import embed_marker, extract_marker, fingerprint_set_hash
from github_client import GitHubFatalError, GitHubTransientError
from schemas import Finding

from store import context_cache, job_store
from store.stages import TERMINAL_STAGES, Stage
from worker import mcp_client
from worker.base import StageTask
from worker.celery_app import celery_app
from worker.exceptions import NonRetryableError, RetryableError

_MAX_RETRIES = int(os.environ.get("MAX_RETRY_ATTEMPTS", "3"))
_BACKOFF_MAX = int(os.environ.get("RETRY_BACKOFF_MAX_SECONDS", "30"))

# TTL for pipeline hand-off data in the Context Cache. Generous relative to
# the worst case retry timeline (3 attempts x ~30s backoff per stage) so a
# slow-but-eventually-successful run never loses its own context.
JOB_CONTEXT_TTL_SECONDS = 3600

_RETRY_KWARGS = dict(
    autoretry_for=(RetryableError,),
    retry_backoff=True,
    retry_backoff_max=_BACKOFF_MAX,
    retry_jitter=True,
    max_retries=_MAX_RETRIES,
)


class FetchContextTask(StageTask):
    stage = Stage.FETCHING_CONTEXT


class AnalyzeTask(StageTask):
    stage = Stage.ANALYZING


class ValidateTask(StageTask):
    stage = Stage.VALIDATING


class PublishTask(StageTask):
    stage = Stage.POSTING_TO_GITHUB


@celery_app.task(bind=True, base=FetchContextTask, **_RETRY_KWARGS)
def fetch_context_task(self, job_id: int) -> None:
    job = job_store.get_job(job_id)
    if job is None or job.stage in TERMINAL_STAGES:
        return

    job_store.record_attempt(job_id, Stage.FETCHING_CONTEXT)
    job_store.transition(job_id, Stage.FETCHING_CONTEXT, message=f"attempt {self.request.retries + 1}")

    owner, repo = job.repo_full_name.split("/", 1)
    try:
        files = mcp_client.get_pr_files(owner, repo, job.pr_number, job.head_sha)
        repo_config = mcp_client.get_repo_config(owner, repo, job.head_sha)
        history_examples = mcp_client.get_history_examples(
            job.repo_full_name, [f["filename"] for f in files]
        )
    except GitHubFatalError as exc:
        raise NonRetryableError(str(exc)) from exc
    except GitHubTransientError as exc:
        raise RetryableError(str(exc)) from exc

    context_cache.set(
        "job_context",
        str(job_id),
        value={"files": files, "repo_config": repo_config, "history_examples": history_examples},
        ttl_seconds=JOB_CONTEXT_TTL_SECONDS,
    )

    analyze_task.delay(job_id)


@celery_app.task(bind=True, base=AnalyzeTask, **_RETRY_KWARGS)
def analyze_task(self, job_id: int) -> None:
    job = job_store.get_job(job_id)
    if job is None or job.stage in TERMINAL_STAGES:
        return

    job_store.record_attempt(job_id, Stage.ANALYZING)
    job_store.transition(job_id, Stage.ANALYZING, message=f"attempt {self.request.retries + 1}")

    context = context_cache.get("job_context", str(job_id))
    if context is None:
        raise NonRetryableError("job context missing/expired before ANALYZING")

    # docs (ARCHITECTURE_DIAGRAMS.md): on a retry, regenerate at temperature=0.
    temperature = 0.0 if self.request.retries > 0 else None

    try:
        findings = agent_core_main.analyze(
            repository_id=job.repository_id,
            pr_number=job.pr_number,
            head_sha=job.head_sha,
            files=context["files"],
            history_examples=context["history_examples"],
            temperature=temperature,
        )
    except LLMFatalError as exc:
        raise NonRetryableError(str(exc)) from exc
    except LLMTransientError as exc:
        raise RetryableError(str(exc)) from exc

    context_cache.set(
        "job_analysis",
        str(job_id),
        value=[f.model_dump() for f in findings],
        ttl_seconds=JOB_CONTEXT_TTL_SECONDS,
    )

    validate_task.delay(job_id)


@celery_app.task(bind=True, base=ValidateTask)
def validate_task(self, job_id: int) -> None:
    job = job_store.get_job(job_id)
    if job is None or job.stage in TERMINAL_STAGES:
        return

    job_store.transition(job_id, Stage.VALIDATING)

    context = context_cache.get("job_context", str(job_id))
    raw_findings = context_cache.get("job_analysis", str(job_id))
    if context is None or raw_findings is None:
        job_store.mark_failed(job_id, Stage.VALIDATING, "context or analysis missing/expired before VALIDATING")
        return

    try:
        findings = [Finding.model_validate(f) for f in raw_findings]
    except ValidationError as exc:
        # Deterministic validation failure: never retried (requirement #12).
        job_store.mark_failed(job_id, Stage.VALIDATING, f"finding schema validation failed: {exc}")
        return

    diff_index = DiffIndex.from_github_files(context["files"])
    valid, rejected = agent_core_main.validate_against_diff(findings, diff_index)

    if rejected:
        job_store.transition(
            job_id,
            Stage.VALIDATING,
            message=f"dropped {len(rejected)} finding(s) not present in the current diff",
        )

    finding_dicts = agent_core_main.to_finding_dicts(
        valid, repository_id=job.repository_id, pr_number=job.pr_number, head_sha=job.head_sha
    )
    job_store.save_findings(job_id, finding_dicts)

    publish_task.delay(job_id)


def _format_comment(f: dict) -> str:
    lines = [f"**[{f['rule_id']}]** `{f['severity']}` (confidence: {f['confidence']:.2f})", "", f["message"]]
    if f.get("suggestion"):
        lines += ["", f"**Suggestion:** {f['suggestion']}"]
    hr = f.get("historical_reference")
    if hr:
        if isinstance(hr, str):
            hr = json.loads(hr)
        lines += ["", f"_Historical reference: PR #{hr['pr']} — {hr['reason']}_"]
    return "\n".join(lines)


def _build_review_body(findings: list[dict]) -> str:
    if not findings:
        return "**PR Guardian** analyzed this revision and found no issues."
    lines = [f"**PR Guardian** found {len(findings)} finding(s) in this revision:", ""]
    for f in findings:
        lines.append(f"- `{f['severity']}` **{f['rule_id']}** — `{f['path']}:{f['line']}`")
    return "\n".join(lines)


@celery_app.task(bind=True, base=PublishTask, **_RETRY_KWARGS)
def publish_task(self, job_id: int) -> None:
    job = job_store.get_job(job_id)
    if job is None or job.stage in TERMINAL_STAGES:
        return

    job_store.record_attempt(job_id, Stage.POSTING_TO_GITHUB)
    job_store.transition(job_id, Stage.POSTING_TO_GITHUB, message=f"attempt {self.request.retries + 1}")

    owner, repo = job.repo_full_name.split("/", 1)

    # Requirement #14: re-check the PR's live head sha right before publishing.
    try:
        current_sha = mcp_client.get_pr_head_sha(owner, repo, job.pr_number)
    except GitHubFatalError as exc:
        raise NonRetryableError(str(exc)) from exc
    except GitHubTransientError as exc:
        raise RetryableError(str(exc)) from exc

    if current_sha != job.head_sha:
        # Deterministic, not transient: this analysis is stale by design.
        raise NonRetryableError(f"stale analysis: PR head is now {current_sha}, analyzed {job.head_sha}")

    findings = job_store.get_findings(job_id)
    fp_hash = fingerprint_set_hash([f["fingerprint"] for f in findings] or [f"empty:{job.head_sha}"])

    # Requirement #15, layer 1: did *this* job already publish (e.g. a
    # retry after we lost the HTTP response, not because GitHub failed)?
    already = job_store.find_completed_review(job.repository_id, job.pr_number, job.head_sha)
    if already is not None and already.fingerprint_set_hash == fp_hash:
        job_store.mark_review_published(job_id, already.github_review_id, fp_hash)
        return

    # Requirement #15, layer 2: does GitHub itself already have a review
    # carrying this exact fingerprint-set marker (belt and suspenders
    # against a crash between a successful POST and our own DB write)?
    try:
        existing_reviews = mcp_client.list_reviews(owner, repo, job.pr_number)
    except GitHubFatalError as exc:
        raise NonRetryableError(str(exc)) from exc
    except GitHubTransientError as exc:
        raise RetryableError(str(exc)) from exc

    for review in existing_reviews:
        if extract_marker(review.get("body") or "") == fp_hash:
            job_store.mark_review_published(job_id, review["id"], fp_hash)
            return

    body = embed_marker(_build_review_body(findings), fp_hash)
    comments = [
        {"path": f["path"], "line": f["line"], "side": f["side"], "body": _format_comment(f)} for f in findings
    ]

    try:
        review = mcp_client.publish_review(
            owner, repo, job.pr_number, commit_id=job.head_sha, body=body, comments=comments
        )
    except GitHubFatalError as exc:
        raise NonRetryableError(str(exc)) from exc
    except GitHubTransientError as exc:
        raise RetryableError(str(exc)) from exc

    job_store.mark_review_published(job_id, review["id"], fp_hash)
