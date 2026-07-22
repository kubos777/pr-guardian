"""PR Guardian - MCP Server.

Exposes GitHub access as MCP tools so the worker never talks to
``github_client`` directly (matches ARCHITECTURE_DIAGRAMS.md: worker ->
MCP -> GitHub). Read-side tools go through the Context Cache (Redis, TTL);
``get_pr_head_sha`` and ``publish_review`` intentionally bypass the cache
since they must reflect the current, live GitHub state (requirement #14).

Error shape: MCP tool exceptions do not cross the client/server boundary
as typed Python exceptions (FastMCP wraps every tool failure in a generic
``ToolError``, discarding the original class - verified empirically). So
GitHub-backed tools never raise; they return an envelope
``{"ok": True, "data": ...}`` or ``{"ok": False, "error": "transient" |
"fatal", "message": ...}`` and ``worker/mcp_client.py`` re-hydrates that
into ``github_client.GitHubTransientError`` / ``GitHubFatalError`` on the
caller side, so the retry classification in requirement #12 still works
whether GitHub was called directly or through MCP.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "github-integration"):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

from fastmcp import FastMCP

import github_client
from github_client import GitHubFatalError, GitHubTransientError
from store import context_cache, history_store

mcp = FastMCP("pr-guardian-context")

CONFIG_FILES = [".eslintrc", ".eslintrc.json", ".eslintrc.js", ".prettierrc", "tsconfig.json"]


def _envelope(fn: Callable[[], Any]) -> dict:
    try:
        return {"ok": True, "data": fn()}
    except GitHubTransientError as exc:
        return {"ok": False, "error": "transient", "message": str(exc)}
    except GitHubFatalError as exc:
        return {"ok": False, "error": "fatal", "message": str(exc)}
    except Exception as exc:  # unexpected bug: never silently retry it
        return {"ok": False, "error": "fatal", "message": f"unexpected error: {exc}"}


@mcp.tool
def get_pr_files(owner: str, repo: str, pr_number: int, head_sha: str) -> dict:
    """Fetch the PR's changed files + unified-diff patches (Context Cache, TTL)."""

    def _fetch():
        cached = context_cache.get("pr_files", owner, repo, str(pr_number), head_sha)
        if cached is not None:
            return cached
        files = github_client.get_pr_files(owner, repo, pr_number)
        context_cache.set("pr_files", owner, repo, str(pr_number), head_sha, value=files)
        return files

    return _envelope(_fetch)


@mcp.tool
def get_pr_head_sha(owner: str, repo: str, pr_number: int) -> dict:
    """Fetch the PR's *current* head SHA. Never cached: requirement #14
    requires this to reflect live GitHub state at publish time.
    """
    return _envelope(lambda: github_client.get_pr_head_sha(owner, repo, pr_number))


@mcp.tool
def get_repo_config(owner: str, repo: str, head_sha: str) -> dict:
    """Fetch known style/config files at this sha (Context Cache, TTL)."""

    def _fetch():
        cached = context_cache.get("repo_config", owner, repo, head_sha)
        if cached is not None:
            return cached
        config = {path: github_client.get_repo_file(owner, repo, path, head_sha) for path in CONFIG_FILES}
        context_cache.set("repo_config", owner, repo, head_sha, value=config)
        return config

    return _envelope(_fetch)


@mcp.tool
def get_history_examples(repo_full_name: str, file_paths: list[str], limit: int = 5) -> list[dict]:
    """Retrieve approved historical examples (History Store). This is a
    retrieval, never a learning step — see store/history_store.py.
    """
    return history_store.get_related_examples(repo_full_name, file_paths, limit=limit)


@mcp.tool
def publish_review(
    owner: str,
    repo: str,
    pr_number: int,
    commit_id: str,
    body: str,
    comments: list[dict],
) -> dict:
    """Requirement #16: publish one batched review with inline comments."""
    return _envelope(
        lambda: github_client.post_review(
            owner, repo, pr_number, commit_id=commit_id, body=body, comments=comments, event="COMMENT"
        )
    )


@mcp.tool
def list_reviews(owner: str, repo: str, pr_number: int) -> dict:
    """List existing reviews on the PR (used for publish-idempotency checks)."""
    return _envelope(lambda: github_client.list_reviews(owner, repo, pr_number))


def start_server():
    """Start the MCP server over stdio (standalone / manual use)."""
    mcp.run()


if __name__ == "__main__":
    start_server()
