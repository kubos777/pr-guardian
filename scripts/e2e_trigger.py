#!/usr/bin/env python3
"""End-to-end trigger for PR Guardian.

Simulates a GitHub `pull_request` webhook delivery hitting the local webhook
handler with a properly signed (HMAC-SHA256) payload, then polls the read
model (`GET /jobs/latest`) until the job reaches a terminal state, printing
each stage transition and the final findings.

This is the "play button" for the demo: it exercises the real ingress path
(signature verification -> job creation -> Celery enqueue) and, when the
worker + real GROQ_API_KEY + GITHUB_TOKEN are configured and the target PR is
open on GitHub, the full pipeline through to published review comments.

Usage:
    uv run python scripts/e2e_trigger.py \
        --repo kubos777/pr-guardian-demo \
        --pr 1 \
        --head-sha <sha> \
        --repo-id 123456789

Environment:
    GITHUB_WEBHOOK_SECRET   must match the running webhook handler's secret
    WEBHOOK_URL             defaults to http://localhost:8000
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.request

TERMINAL = {"COMPLETED", "FAILED"}


def build_payload(repo: str, repo_id: int, pr: int, head_sha: str, author: str, title: str) -> dict:
    owner, name = repo.split("/", 1)
    return {
        "action": "opened",
        "number": pr,
        "pull_request": {
            "number": pr,
            "title": title,
            "user": {"login": author},
            "head": {"ref": "ft/add-user-features", "sha": head_sha},
            "base": {"ref": "main"},
        },
        "repository": {
            "id": repo_id,
            "full_name": repo,
            "name": name,
            "owner": {"login": owner},
        },
        "sender": {"login": author},
    }


def sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def post_webhook(url: str, body: bytes, secret: str, delivery_id: str) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"{url}/webhook",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": delivery_id,
            "X-Hub-Signature-256": sign(body, secret),
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode()}


def get_latest(url: str) -> dict:
    with urllib.request.urlopen(f"{url}/jobs/latest") as resp:
        return json.loads(resp.read())


def main() -> int:
    parser = argparse.ArgumentParser(description="Trigger PR Guardian end-to-end")
    parser.add_argument("--repo", default="kubos777/pr-guardian-demo")
    parser.add_argument("--repo-id", type=int, default=999000001)
    parser.add_argument("--pr", type=int, default=1)
    parser.add_argument("--head-sha", required=True, help="head commit SHA of the PR branch")
    parser.add_argument("--author", default="dev-user")
    parser.add_argument("--title", default="feat: add user features")
    parser.add_argument("--timeout", type=int, default=90, help="seconds to wait for terminal state")
    args = parser.parse_args()

    secret = os.environ.get("GITHUB_WEBHOOK_SECRET")
    if not secret:
        print("ERROR: GITHUB_WEBHOOK_SECRET not set in environment.", file=sys.stderr)
        return 1

    url = os.environ.get("WEBHOOK_URL", "http://localhost:8000")
    delivery_id = f"e2e-{int(time.time())}"

    payload = build_payload(args.repo, args.repo_id, args.pr, args.head_sha, args.author, args.title)
    body = json.dumps(payload).encode("utf-8")

    print(f"→ POST {url}/webhook  (delivery {delivery_id})")
    status, resp = post_webhook(url, body, secret, delivery_id)
    print(f"← {status} {json.dumps(resp)}")

    if status != 202:
        print("Webhook was not accepted (expected 202). Aborting.", file=sys.stderr)
        return 1

    print("\nPolling /jobs/latest until terminal state...\n")
    last_status = None
    deadline = time.time() + args.timeout
    while time.time() < deadline:
        latest = get_latest(url)
        job = latest.get("job")
        if job is None:
            time.sleep(1)
            continue
        if job["status"] != last_status:
            print(f"  [{time.strftime('%H:%M:%S')}] status = {job['status']}"
                  + (f"  error: {job['error']}" if job.get("error") else ""))
            last_status = job["status"]
        if job["status"] in TERMINAL:
            findings = latest.get("findings", [])
            print(f"\n=== FINAL: {job['status']} — {len(findings)} finding(s) ===")
            for f in findings:
                print(f"  · [{f.get('severity')}] {f.get('rule_id')} — {f.get('path')}:{f.get('line')}")
                print(f"    {f.get('message')}")
            return 0 if job["status"] == "COMPLETED" else 2
        time.sleep(1)

    print("Timed out waiting for a terminal state.", file=sys.stderr)
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
