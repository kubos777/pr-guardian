"""Verification suite for the async, durable PR Guardian review pipeline.

Runs fully offline: no live Redis, GitHub, or LLM required.
- Redis (Context Cache) is replaced by tests.fakes.FakeRedis.
- GitHub (via MCP) and the LLM (agent-core.main.analyze) are monkeypatched
  at the worker.tasks call sites.
- Celery runs in eager mode (task_always_eager=True,
  task_eager_propagates=False), which — verified empirically — still runs
  the real autoretry/backoff/on_failure machinery synchronously, so the
  retry-vs-fail-immediately split (requirements #12/#13) is exercised for
  real, not merely asserted about.

Run with:
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "agent-core", _REPO_ROOT / "github-integration"):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

os.environ.setdefault("GITHUB_WEBHOOK_SECRET", "test-secret")
os.environ.setdefault("GITHUB_TOKEN", "test-token")
os.environ.setdefault("LLM_API_KEY", "test-key")

import store.db as db
import store.context_cache as context_cache
import store.job_store as job_store
from store.stages import Stage
from tests.fakes import FakeRedis

import schemas
from diff_utils import DiffIndex, parse_patch
from fingerprint import embed_marker, extract_marker, finding_fingerprint

import webhook_handler
from github_client import GitHubFatalError, GitHubTransientError

from worker.celery_app import celery_app
from worker import tasks as pipeline_tasks

# Sample unified-diff hunk for one file: RIGHT (new) lines 1-4 are
# commentable, LEFT (old) lines 1-3 are commentable.
SAMPLE_PATCH = (
    "@@ -1,3 +1,4 @@\n"
    " context line 1\n"
    "-removed line\n"
    "+added line 1\n"
    "+added line 2\n"
    " context line 2"
)
SAMPLE_FILES = [{"filename": "src/config/secrets.ts", "patch": SAMPLE_PATCH}]


def _reset_db() -> str:
    """Point the Job Store at a fresh temp SQLite file for this test."""
    db._local.conn = None
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)  # let init_db create it fresh
    os.environ["PR_GUARDIAN_DB_PATH"] = path
    db.init_db()
    return path


class SignatureValidationTests(unittest.TestCase):
    """Requirement #1: X-Hub-Signature-256 validated before parsing/processing."""

    def test_valid_signature_accepted(self):
        secret = "shh"
        body = b'{"action": "opened"}'
        import hashlib
        import hmac

        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        self.assertTrue(webhook_handler.verify_signature(body, sig, secret))

    def test_tampered_body_rejected(self):
        secret = "shh"
        body = b'{"action": "opened"}'
        import hashlib
        import hmac

        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        tampered_body = b'{"action": "closed"}'
        self.assertFalse(webhook_handler.verify_signature(tampered_body, sig, secret))

    def test_missing_signature_rejected(self):
        self.assertFalse(webhook_handler.verify_signature(b"{}", None, "shh"))

    def test_wrong_prefix_rejected(self):
        self.assertFalse(webhook_handler.verify_signature(b"{}", "sha1=deadbeef", "shh"))


class DiffUtilsTests(unittest.TestCase):
    def test_parse_patch_line_sets(self):
        right, left = parse_patch(SAMPLE_PATCH)
        self.assertEqual(right, {1, 2, 3, 4})
        self.assertEqual(left, {1, 2, 3})

    def test_diff_index_commentable(self):
        idx = DiffIndex.from_github_files(SAMPLE_FILES)
        self.assertTrue(idx.is_commentable("src/config/secrets.ts", 3, "RIGHT"))
        self.assertTrue(idx.is_commentable("src/config/secrets.ts", 2, "LEFT"))
        self.assertFalse(idx.is_commentable("src/config/secrets.ts", 999, "RIGHT"))
        self.assertFalse(idx.is_commentable("no/such/file.ts", 1, "RIGHT"))


class FingerprintTests(unittest.TestCase):
    def test_deterministic(self):
        kwargs = dict(repository_id=1, pr_number=2, head_sha="abc", rule_id="r", path="p", line=1, message="m")
        self.assertEqual(finding_fingerprint(**kwargs), finding_fingerprint(**kwargs))

    def test_differs_on_message(self):
        kwargs = dict(repository_id=1, pr_number=2, head_sha="abc", rule_id="r", path="p", line=1)
        a = finding_fingerprint(message="one", **kwargs)
        b = finding_fingerprint(message="two", **kwargs)
        self.assertNotEqual(a, b)

    def test_marker_roundtrip(self):
        body = embed_marker("**PR Guardian** found 1 finding(s).", "deadbeef")
        self.assertEqual(extract_marker(body), "deadbeef")
        self.assertIsNone(extract_marker("no marker here"))


class FindingSchemaTests(unittest.TestCase):
    def test_valid_finding(self):
        f = schemas.Finding(
            rule_id="secret_exposure", severity="high", confidence=0.9, path="src/a.ts", line=3, message="m"
        )
        self.assertEqual(f.side, "RIGHT")

    def test_rejects_path_traversal(self):
        with self.assertRaises(Exception):
            schemas.Finding(
                rule_id="r", severity="high", confidence=0.9, path="../../etc/passwd", line=1, message="m"
            )

    def test_rejects_confidence_out_of_range(self):
        with self.assertRaises(Exception):
            schemas.Finding(rule_id="r", severity="high", confidence=1.5, path="a.ts", line=1, message="m")


class JobStoreDedupTests(unittest.TestCase):
    def setUp(self):
        _reset_db()

    def test_create_job_happy_path(self):
        job, created, reason = job_store.create_job(
            delivery_id="d1", repository_id=1, repo_full_name="acme/widgets", pr_number=42, head_sha="sha1", action="opened"
        )
        self.assertTrue(created)
        self.assertEqual(reason, "created")
        self.assertEqual(job.status, Stage.RECEIVED.value)

    def test_duplicate_delivery_is_deduped(self):
        job1, created1, _ = job_store.create_job(
            delivery_id="d1", repository_id=1, repo_full_name="acme/widgets", pr_number=42, head_sha="sha1", action="opened"
        )
        job2, created2, reason2 = job_store.create_job(
            delivery_id="d1", repository_id=1, repo_full_name="acme/widgets", pr_number=42, head_sha="sha1", action="opened"
        )
        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(reason2, "duplicate_delivery")
        self.assertEqual(job1.id, job2.id)

    def test_duplicate_review_different_delivery_same_sha_is_deduped(self):
        job1, _, _ = job_store.create_job(
            delivery_id="d1", repository_id=1, repo_full_name="acme/widgets", pr_number=42, head_sha="sha1", action="opened"
        )
        job2, created2, reason2 = job_store.create_job(
            delivery_id="d2", repository_id=1, repo_full_name="acme/widgets", pr_number=42, head_sha="sha1", action="synchronize"
        )
        self.assertFalse(created2)
        self.assertEqual(reason2, "duplicate_review")
        self.assertEqual(job1.id, job2.id)

    def test_failed_job_does_not_block_retry_for_same_sha(self):
        job1, _, _ = job_store.create_job(
            delivery_id="d1", repository_id=1, repo_full_name="acme/widgets", pr_number=42, head_sha="sha1", action="opened"
        )
        job_store.mark_failed(job1.id, Stage.FETCHING_CONTEXT, "boom")
        job2, created2, reason2 = job_store.create_job(
            delivery_id="d2", repository_id=1, repo_full_name="acme/widgets", pr_number=42, head_sha="sha1", action="synchronize"
        )
        self.assertTrue(created2)
        self.assertEqual(reason2, "created")
        self.assertNotEqual(job1.id, job2.id)

    def test_job_events_persisted_on_transition(self):
        job, _, _ = job_store.create_job(
            delivery_id="d1", repository_id=1, repo_full_name="acme/widgets", pr_number=42, head_sha="sha1", action="opened"
        )
        job_store.transition(job.id, Stage.QUEUED, "enqueued")
        events = job_store.get_job_events(job.id)
        statuses = [e["to_status"] for e in events]
        self.assertEqual(statuses, [Stage.RECEIVED.value, Stage.QUEUED.value])


class PipelineIntegrationTests(unittest.TestCase):
    """End-to-end worker pipeline, everything external mocked."""

    def setUp(self):
        _reset_db()
        context_cache._client = FakeRedis()
        celery_app.conf.task_always_eager = True
        celery_app.conf.task_eager_propagates = False

        self.job, _, _ = job_store.create_job(
            delivery_id="d1", repository_id=1, repo_full_name="acme/widgets", pr_number=42, head_sha="sha1", action="opened"
        )
        job_store.transition(self.job.id, Stage.QUEUED, "enqueued")

        fake_finding = schemas.Finding(
            rule_id="secret_exposure",
            severity="high",
            confidence=0.9,
            path="src/config/secrets.ts",
            line=3,
            side="RIGHT",
            message="Hardcoded API key",
            suggestion="Use process.env.API_KEY",
        )
        self.analyze_patch = patch.object(pipeline_tasks.agent_core_main, "analyze", return_value=[fake_finding])
        self.analyze_patch.start()

        self.mcp_get_files = patch.object(
            pipeline_tasks.mcp_client, "get_pr_files", return_value=SAMPLE_FILES
        )
        self.mcp_get_files.start()
        self.mcp_get_config = patch.object(pipeline_tasks.mcp_client, "get_repo_config", return_value={})
        self.mcp_get_config.start()
        self.mcp_get_history = patch.object(pipeline_tasks.mcp_client, "get_history_examples", return_value=[])
        self.mcp_get_history.start()
        self.mcp_head_sha = patch.object(pipeline_tasks.mcp_client, "get_pr_head_sha", return_value="sha1")
        self.mcp_head_sha.start()
        self.mcp_list_reviews = patch.object(pipeline_tasks.mcp_client, "list_reviews", return_value=[])
        self.mcp_list_reviews.start()
        self.mcp_publish = patch.object(
            pipeline_tasks.mcp_client, "publish_review", return_value={"id": 999}
        )
        self.mcp_publish.start()

    def tearDown(self):
        patch.stopall()

    def test_happy_path_reaches_completed(self):
        pipeline_tasks.fetch_context_task.delay(self.job.id)

        job = job_store.get_job(self.job.id)
        self.assertEqual(job.status, Stage.COMPLETED.value)
        self.assertEqual(job.github_review_id, 999)

        findings = job_store.get_findings(self.job.id)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["rule_id"], "secret_exposure")

        statuses = [e["to_status"] for e in job_store.get_job_events(self.job.id)]
        for expected in (
            Stage.RECEIVED.value,
            Stage.QUEUED.value,
            Stage.FETCHING_CONTEXT.value,
            Stage.ANALYZING.value,
            Stage.VALIDATING.value,
            Stage.POSTING_TO_GITHUB.value,
            Stage.COMPLETED.value,
        ):
            self.assertIn(expected, statuses)

        self.mcp_publish_mock_calls = pipeline_tasks.mcp_client.publish_review
        self.assertEqual(pipeline_tasks.mcp_client.publish_review.call_count, 1)

    def test_retryable_github_fetch_error_recovers(self):
        calls = {"n": 0}

        def flaky_get_pr_files(owner, repo, pr_number, head_sha):
            calls["n"] += 1
            if calls["n"] < 3:
                raise GitHubTransientError("simulated timeout")
            return SAMPLE_FILES

        self.mcp_get_files.stop()
        patch.object(pipeline_tasks.mcp_client, "get_pr_files", side_effect=flaky_get_pr_files).start()

        pipeline_tasks.fetch_context_task.delay(self.job.id)

        job = job_store.get_job(self.job.id)
        self.assertEqual(job.status, Stage.COMPLETED.value)
        self.assertEqual(calls["n"], 3)
        self.assertEqual(job.attempt_counts.get(Stage.FETCHING_CONTEXT.value), 3)

    def test_nonretryable_github_fetch_error_fails_after_one_attempt(self):
        self.mcp_get_files.stop()
        patch.object(
            pipeline_tasks.mcp_client, "get_pr_files", side_effect=GitHubFatalError("403 forbidden")
        ).start()

        pipeline_tasks.fetch_context_task.delay(self.job.id)

        job = job_store.get_job(self.job.id)
        self.assertEqual(job.status, Stage.FAILED.value)
        self.assertIn("403 forbidden", job.error)
        self.assertEqual(job.attempt_counts.get(Stage.FETCHING_CONTEXT.value), 1)

    def test_stale_head_sha_fails_without_retry(self):
        self.mcp_head_sha.stop()
        patch.object(pipeline_tasks.mcp_client, "get_pr_head_sha", return_value="a-different-sha").start()

        pipeline_tasks.fetch_context_task.delay(self.job.id)

        job = job_store.get_job(self.job.id)
        self.assertEqual(job.status, Stage.FAILED.value)
        self.assertIn("stale analysis", job.error)
        self.assertEqual(job.attempt_counts.get(Stage.POSTING_TO_GITHUB.value), 1)
        pipeline_tasks.mcp_client.publish_review.assert_not_called()

    def test_republish_detects_existing_marker_on_github(self):
        """Requirement #15, defense-in-depth layer: if the process crashed
        after GitHub accepted the review but before we recorded that fact,
        a retry must recognize the fingerprint-set marker already on
        GitHub and not post a second review.
        """
        pipeline_tasks.fetch_context_task.delay(self.job.id)
        job = job_store.get_job(self.job.id)
        self.assertEqual(job.status, Stage.COMPLETED.value)
        self.assertEqual(pipeline_tasks.mcp_client.publish_review.call_count, 1)

        _, posted_kwargs = pipeline_tasks.mcp_client.publish_review.call_args
        posted_body = posted_kwargs["body"]

        # Simulate: crashed after GitHub accepted the POST, before
        # mark_review_published() ran — job is still mid-stage and a
        # retry (or a manual re-trigger) fires publish_task again.
        job_store.transition(self.job.id, Stage.POSTING_TO_GITHUB, "simulated retry after crash")
        self.mcp_list_reviews.stop()
        patch.object(
            pipeline_tasks.mcp_client, "list_reviews", return_value=[{"id": 999, "body": posted_body}]
        ).start()

        pipeline_tasks.publish_task.delay(self.job.id)

        self.assertEqual(pipeline_tasks.mcp_client.publish_review.call_count, 1)
        job = job_store.get_job(self.job.id)
        self.assertEqual(job.status, Stage.COMPLETED.value)
        self.assertEqual(job.github_review_id, 999)


class WebhookEndpointTests(unittest.TestCase):
    """End-to-end HTTP layer: requirements #1, #2, #5 together."""

    def setUp(self):
        _reset_db()
        self.secret = os.environ["GITHUB_WEBHOOK_SECRET"]
        self.enqueue_patch = patch.object(pipeline_tasks.fetch_context_task, "delay")
        self.enqueue_mock = self.enqueue_patch.start()

        from fastapi.testclient import TestClient

        self.client = TestClient(webhook_handler.app)

    def tearDown(self):
        patch.stopall()

    def _sign(self, body: bytes) -> str:
        import hashlib
        import hmac

        return "sha256=" + hmac.new(self.secret.encode(), body, hashlib.sha256).hexdigest()

    def _payload(self, action="opened", pr_number=42, head_sha="sha1", repo_id=1):
        import json as _json

        body = _json.dumps(
            {
                "action": action,
                "repository": {"id": repo_id, "full_name": "acme/widgets"},
                "pull_request": {"number": pr_number, "head": {"sha": head_sha}},
            }
        ).encode()
        return body

    def test_valid_opened_event_returns_202_and_enqueues(self):
        body = self._payload()
        resp = self.client.post(
            "/webhook",
            content=body,
            headers={
                "X-Hub-Signature-256": self._sign(body),
                "X-GitHub-Event": "pull_request",
                "X-GitHub-Delivery": "delivery-1",
                "Content-Type": "application/json",
            },
        )
        self.assertEqual(resp.status_code, 202)
        self.assertEqual(resp.json()["dedup"], "created")
        self.enqueue_mock.assert_called_once()

    def test_invalid_signature_returns_401(self):
        body = self._payload()
        resp = self.client.post(
            "/webhook",
            content=body,
            headers={
                "X-Hub-Signature-256": "sha256=deadbeef",
                "X-GitHub-Event": "pull_request",
                "X-GitHub-Delivery": "delivery-1",
                "Content-Type": "application/json",
            },
        )
        self.assertEqual(resp.status_code, 401)
        self.enqueue_mock.assert_not_called()

    def test_unsupported_action_ignored_without_enqueue(self):
        body = self._payload(action="closed")
        resp = self.client.post(
            "/webhook",
            content=body,
            headers={
                "X-Hub-Signature-256": self._sign(body),
                "X-GitHub-Event": "pull_request",
                "X-GitHub-Delivery": "delivery-1",
                "Content-Type": "application/json",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ignored")
        self.enqueue_mock.assert_not_called()

    def test_duplicate_delivery_returns_202_without_second_enqueue(self):
        body = self._payload()
        headers = {
            "X-Hub-Signature-256": self._sign(body),
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": "delivery-1",
            "Content-Type": "application/json",
        }
        resp1 = self.client.post("/webhook", content=body, headers=headers)
        resp2 = self.client.post("/webhook", content=body, headers=headers)

        self.assertEqual(resp1.status_code, 202)
        self.assertEqual(resp2.status_code, 202)
        self.assertEqual(resp2.json()["dedup"], "duplicate_delivery")
        self.assertEqual(resp1.json()["job_id"], resp2.json()["job_id"])
        self.enqueue_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
