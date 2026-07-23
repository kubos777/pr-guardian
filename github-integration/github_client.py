"""Thin GitHub REST API client used by the MCP server (server.py).

Every network call here is classified into exactly the buckets requirement
#12 asks for: timeout / 429 / 5xx are transient (``GitHubTransientError``,
worth retrying), 401/403 and other deterministic 4xx are fatal
(``GitHubFatalError``, never retried). Callers (the MCP tools in
server.py) never see raw httpx exceptions.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx

GITHUB_API_URL = os.environ.get("GITHUB_API_URL", "https://api.github.com")


class GitHubTransientError(Exception):
    """Timeout, 429, or 5xx — safe to retry."""


class GitHubFatalError(Exception):
    """401/403 or another non-retryable GitHub API failure."""


def _token() -> str:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise GitHubFatalError("GITHUB_TOKEN is not configured")
    return token


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_token()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _request(method: str, path: str, *, json_body: Optional[dict] = None, timeout: float = 15.0) -> Any:
    url = f"{GITHUB_API_URL}{path}"
    try:
        resp = httpx.request(method, url, headers=_headers(), json=json_body, timeout=timeout)
    except httpx.TimeoutException as exc:
        raise GitHubTransientError(f"timeout calling {method} {path}: {exc}") from exc
    except httpx.HTTPError as exc:
        raise GitHubTransientError(f"network error calling {method} {path}: {exc}") from exc

    if resp.status_code in (401, 403):
        raise GitHubFatalError(f"{method} {path} -> {resp.status_code}: {resp.text[:300]}")
    if resp.status_code == 429 or resp.status_code >= 500:
        raise GitHubTransientError(f"{method} {path} -> {resp.status_code}: {resp.text[:300]}")
    if resp.status_code >= 400:
        # Deterministic client error (404 not found, 422 validation, ...) - not retryable.
        raise GitHubFatalError(f"{method} {path} -> {resp.status_code}: {resp.text[:300]}")

    if resp.status_code == 204 or not resp.content:
        return None
    return resp.json()


def get_pr(owner: str, repo: str, pr_number: int) -> dict:
    return _request("GET", f"/repos/{owner}/{repo}/pulls/{pr_number}")


def get_pr_head_sha(owner: str, repo: str, pr_number: int) -> str:
    return get_pr(owner, repo, pr_number)["head"]["sha"]


def get_pr_files(owner: str, repo: str, pr_number: int) -> list[dict]:
    files: list[dict] = []
    page = 1
    while True:
        batch = _request(
            "GET", f"/repos/{owner}/{repo}/pulls/{pr_number}/files?per_page=100&page={page}"
        )
        if not batch:
            break
        files.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return files


def get_repo_file(owner: str, repo: str, path: str, ref: str) -> Optional[str]:
    """Fetch a config file's raw text (e.g. .eslintrc). Returns None if it
    doesn't exist rather than raising, since absence is expected/common.
    """
    import base64

    try:
        data = _request("GET", f"/repos/{owner}/{repo}/contents/{path}?ref={ref}")
    except GitHubFatalError as exc:
        if "404" in str(exc):
            return None
        raise
    if data is None or "content" not in data:
        return None
    return base64.b64decode(data["content"]).decode("utf-8", errors="replace")


def list_reviews(owner: str, repo: str, pr_number: int) -> list[dict]:
    return _request("GET", f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews?per_page=100") or []


def post_review(
    owner: str,
    repo: str,
    pr_number: int,
    *,
    commit_id: str,
    body: str,
    comments: list[dict],
    event: str = "COMMENT",
) -> dict:
    """Requirement #16: publish multiple inline comments in one call via
    POST /repos/{owner}/{repo}/pulls/{pull_number}/reviews.
    """
    payload = {
        "commit_id": commit_id,
        "body": body,
        "event": event,
        "comments": comments,
    }
    return _request("POST", f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews", json_body=payload)
