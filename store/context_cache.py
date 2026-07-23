"""Context Cache — ephemeral GitHub API / repo-config data, TTL-based (Redis).

This is intentionally *not* SQLite and *not* durable: it exists purely to
avoid re-hitting the GitHub API for the same (repo, sha, resource) within a
short window. Losing it changes nothing about correctness — the MCP server
just re-fetches from GitHub. Never store execution state or findings here;
that belongs in the Job Store (``store/job_store.py``).
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

import redis

_DEFAULT_TTL_SECONDS = int(os.environ.get("CONTEXT_CACHE_TTL_SECONDS", "300"))
_REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

_client: Optional[redis.Redis] = None


def _redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(_REDIS_URL, decode_responses=True)
    return _client


def _key(namespace: str, *parts: str) -> str:
    return "ctx:" + namespace + ":" + ":".join(str(p) for p in parts)


def get(namespace: str, *parts: str) -> Optional[Any]:
    raw = _redis().get(_key(namespace, *parts))
    if raw is None:
        return None
    return json.loads(raw)


def set(namespace: str, *parts: str, value: Any, ttl_seconds: int | None = None) -> None:
    _redis().setex(
        _key(namespace, *parts),
        ttl_seconds if ttl_seconds is not None else _DEFAULT_TTL_SECONDS,
        json.dumps(value),
    )


def invalidate(namespace: str, *parts: str) -> None:
    _redis().delete(_key(namespace, *parts))
