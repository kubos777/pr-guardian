"""Worker-side MCP client.

This is the *only* way ``worker/tasks.py`` reaches GitHub data — matching
ARCHITECTURE_DIAGRAMS.md's worker -> MCP -> GitHub flow. It talks to the
FastMCP server instance in ``github-integration/server.py`` over an
in-memory transport (no extra process/network hop needed since worker and
MCP server share the same Python runtime), then re-hydrates the
``{"ok": ..., "error": ...}`` envelope (see server.py's module docstring)
back into ``github_client.GitHubTransientError`` / ``GitHubFatalError`` so
``worker/tasks.py`` can classify failures uniformly.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "agent-core", _REPO_ROOT / "github-integration"):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

from fastmcp import Client

from github_client import GitHubFatalError, GitHubTransientError
from server import mcp


def _run(coro):
    return asyncio.run(coro)


async def _call_tool(tool_name: str, **kwargs) -> Any:
    async with Client(mcp) as client:
        result = await client.call_tool(tool_name, kwargs)
        return result.data


def _unwrap(envelope: dict) -> Any:
    if envelope.get("ok"):
        return envelope["data"]
    if envelope.get("error") == "transient":
        raise GitHubTransientError(envelope.get("message", "transient MCP/GitHub error"))
    raise GitHubFatalError(envelope.get("message", "fatal MCP/GitHub error"))


def get_pr_files(owner: str, repo: str, pr_number: int, head_sha: str) -> list[dict]:
    return _unwrap(_run(_call_tool("get_pr_files", owner=owner, repo=repo, pr_number=pr_number, head_sha=head_sha)))


def get_pr_head_sha(owner: str, repo: str, pr_number: int) -> str:
    return _unwrap(_run(_call_tool("get_pr_head_sha", owner=owner, repo=repo, pr_number=pr_number)))


def get_repo_config(owner: str, repo: str, head_sha: str) -> dict:
    return _unwrap(_run(_call_tool("get_repo_config", owner=owner, repo=repo, head_sha=head_sha)))


def get_history_examples(repo_full_name: str, file_paths: list[str], limit: int = 5) -> list[dict]:
    return _run(_call_tool("get_history_examples", repo_full_name=repo_full_name, file_paths=file_paths, limit=limit))


def publish_review(owner: str, repo: str, pr_number: int, commit_id: str, body: str, comments: list[dict]) -> dict:
    return _unwrap(
        _run(
            _call_tool(
                "publish_review",
                owner=owner,
                repo=repo,
                pr_number=pr_number,
                commit_id=commit_id,
                body=body,
                comments=comments,
            )
        )
    )


def list_reviews(owner: str, repo: str, pr_number: int) -> list[dict]:
    return _unwrap(_run(_call_tool("list_reviews", owner=owner, repo=repo, pr_number=pr_number)))
