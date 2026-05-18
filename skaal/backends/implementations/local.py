"""Local in-memory backend implementations and helper re-exports."""

from __future__ import annotations

import builtins
import time
from typing import Any

from skaal.storage import _deserialize as _deserialize
from skaal.storage import _list_page_from_entries as _list_page_from_entries
from skaal.storage import _query_index_from_entries as _query_index_from_entries
from skaal.storage import _scan_page_from_entries as _scan_page_from_entries
from skaal.storage import _serialize as _serialize
from skaal.sync import run as _sync_bridge_run

_sync_run = _sync_bridge_run


class LocalMap:
    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._expires_at: dict[str, float] = {}
        import asyncio

        self._lock = asyncio.Lock()

    def _deadline(self, ttl: float | None) -> float | None:
        if ttl is None:
            return None
        return time.time() + ttl

    def _purge_expired_locked(self) -> None:
        now = time.time()
        expired_keys = [key for key, deadline in self._expires_at.items() if deadline <= now]
        for key in expired_keys:
            self._data.pop(key, None)
            self._expires_at.pop(key, None)

    async def get(self, key: str) -> Any | None:
        async with self._lock:
            self._purge_expired_locked()
            return self._data.get(key)

    async def set(self, key: str, value: Any, *, ttl: float | None = None) -> None:
        async with self._lock:
            self._purge_expired_locked()
            self._data[key] = value
            deadline = self._deadline(ttl)
            if deadline is None:
                self._expires_at.pop(key, None)
            else:
                self._expires_at[key] = deadline

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._data.pop(key, None)
            self._expires_at.pop(key, None)

    async def list(self) -> list[tuple[str, Any]]:
        async with self._lock:
            self._purge_expired_locked()
            return list(self._data.items())

    async def list_page(self, *, limit: int, cursor: str | None):
        return _list_page_from_entries(await self.list(), limit=limit, cursor=cursor)

    async def scan(self, prefix: str = "") -> builtins.list[tuple[str, Any]]:
        async with self._lock:
            self._purge_expired_locked()
            return [(k, v) for k, v in self._data.items() if k.startswith(prefix)]

    async def scan_page(self, prefix: str = "", *, limit: int, cursor: str | None):
        return _scan_page_from_entries(
            await self.scan(prefix),
            prefix=prefix,
            limit=limit,
            cursor=cursor,
        )

    async def query_index(
        self,
        index_name: str,
        key: Any,
        *,
        limit: int,
        cursor: str | None,
    ):
        return _query_index_from_entries(
            await self.list(),
            backend=self,
            index_name=index_name,
            key=key,
            limit=limit,
            cursor=cursor,
        )

    async def ensure_indexes(self) -> None:
        return None

    async def increment_counter(self, key: str, delta: int = 1) -> int:
        async with self._lock:
            current = int(self._data.get(key, 0))
            new_value = current + delta
            self._data[key] = new_value
            return new_value

    async def atomic_update(self, key: str, fn: Any, *, ttl: float | None = None) -> Any:
        async with self._lock:
            self._purge_expired_locked()
            current = self._data.get(key)
            updated = fn(current)
            self._data[key] = updated
            deadline = self._deadline(ttl)
            if deadline is None:
                self._expires_at.pop(key, None)
            else:
                self._expires_at[key] = deadline
            return updated

    async def close(self) -> None:
        pass

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return f"LocalMap({len(self._data)} keys)"


__all__ = [
    "LocalMap",
    "_deserialize",
    "_list_page_from_entries",
    "_query_index_from_entries",
    "_scan_page_from_entries",
    "_serialize",
    "_sync_run",
]
