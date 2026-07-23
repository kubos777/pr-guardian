"""Minimal in-memory stand-in for the redis client, used only in tests.

No live Redis server is required to run the test suite. Implements just
the three methods ``store/context_cache.py`` actually calls.
"""

from __future__ import annotations

import time


class FakeRedis:
    def __init__(self):
        self._store: dict[str, tuple[float | None, str]] = {}

    def get(self, key: str):
        item = self._store.get(key)
        if item is None:
            return None
        expire_at, value = item
        if expire_at is not None and time.time() > expire_at:
            del self._store[key]
            return None
        return value

    def setex(self, key: str, ttl: int, value: str) -> None:
        self._store[key] = (time.time() + ttl, value)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)
