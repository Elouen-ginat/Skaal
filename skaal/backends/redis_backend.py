"""Async Redis storage backend using redis.asyncio."""

from __future__ import annotations

import asyncio
import base64
import json
import math
from typing import Any, Callable, List

from skaal.errors import SkaalConflict, SkaalUnavailable
from skaal.storage import (
    _cursor_identity,
    _encode_cursor,
    _field_value,
    _get_backend_indexes,
    _normalize_limit,
    _sort_token,
    _validate_cursor,
)
from skaal.types.storage import Page


class RedisBackend:
    """
    Redis storage backend using redis.asyncio.

    Keys are stored as: skaal:{namespace}:{key}
    Values are JSON-serialized.

    scan(prefix) uses SCAN with MATCH pattern.
    list() uses SCAN * then MGET.

    Connection is lazy and **per event-loop**: each asyncio event loop that
    uses this backend gets its own redis.asyncio client and connection pool.
    This avoids "Future attached to a different loop" errors when the same
    backend instance is shared between the scheduler daemon thread (which has
    its own loop) and the sync-bridge background loop used by Dash callbacks.
    """

    def __init__(self, url: str = "redis://localhost:6379", namespace: str = "default") -> None:
        self.url = url
        self.namespace = namespace
        # Keyed by id(event_loop) so every loop gets its own connection pool.
        self._clients: dict[int, Any] = {}

    def _key(self, key: str) -> str:
        return f"skaal:{self.namespace}:{key}"

    def _strip_prefix(self, full_key: str) -> str:
        prefix = f"skaal:{self.namespace}:"
        if full_key.startswith(prefix):
            return full_key[len(prefix) :]
        return full_key

    def _key_index(self) -> str:
        return f"skaal:{self.namespace}:__keys__"

    def _index_bucket_key(self, index_name: str, partition_key: Any) -> str:
        token = base64.urlsafe_b64encode(
            json.dumps(partition_key, sort_keys=True, default=str).encode("utf-8")
        ).decode("ascii")
        return f"skaal:{self.namespace}:__idx__:{index_name}:{token}"

    def _ttl_px(self, ttl: float | None) -> int | None:
        if ttl is None:
            return None
        return max(1, math.ceil(ttl * 1000))

    async def _rewrite_index_bucket(
        self,
        client: Any,
        *,
        index_name: str,
        partition_key: Any,
        mutator: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
    ) -> None:
        bucket_key = self._index_bucket_key(index_name, partition_key)
        raw_entries = await client.lrange(bucket_key, 0, -1)
        entries = [json.loads(entry) for entry in raw_entries]
        updated = mutator(entries)
        updated.sort(key=lambda item: (_sort_token(item.get("sort")), item["pk"]))
        pipe = client.pipeline(transaction=True)
        pipe.delete(bucket_key)
        if updated:
            pipe.rpush(bucket_key, *[json.dumps(entry) for entry in updated])
        await pipe.execute()

    async def _ensure_key_index(self, client: Any) -> None:
        if await client.zcard(self._key_index()) > 0:
            return
        pattern = f"skaal:{self.namespace}:*"
        keys: list[str] = []
        async for full_key in client.scan_iter(match=pattern):
            stripped = self._strip_prefix(full_key)
            if stripped.startswith("__"):
                continue
            keys.append(stripped)
        if keys:
            await client.zadd(self._key_index(), {key: 0 for key in keys})

    async def _remove_stale_key_index_members(self, client: Any, keys: list[str]) -> None:
        for key in keys:
            await client.zrem(self._key_index(), key)

    async def _collect_live_key_items(
        self,
        client: Any,
        *,
        min_value: str,
        max_value: str,
        limit: int,
    ) -> list[tuple[str, Any]]:
        collected: list[tuple[str, Any]] = []
        cursor = min_value
        fetch_size = max(limit * 2, 50)

        while len(collected) < limit + 1:
            keys = await client.zrangebylex(
                self._key_index(),
                cursor,
                max_value,
                start=0,
                num=fetch_size,
            )
            if not keys:
                break

            values = await client.mget(*[self._key(key) for key in keys])
            stale_keys: list[str] = []
            for key, value in zip(keys, values):
                if value is None:
                    stale_keys.append(key)
                    continue
                collected.append((key, json.loads(value)))
                if len(collected) >= limit + 1:
                    break

            if stale_keys:
                await self._remove_stale_key_index_members(client, stale_keys)

            if len(keys) < fetch_size or len(collected) >= limit + 1:
                break
            cursor = f"({keys[-1]}"

        return collected

    async def _sync_indexes(self, client: Any, key: str, old_value: Any, new_value: Any) -> None:
        for index_name, index in _get_backend_indexes(self).items():
            old_partition = (
                _field_value(old_value, index.partition_key) if old_value is not None else None
            )
            new_partition = (
                _field_value(new_value, index.partition_key) if new_value is not None else None
            )

            if old_partition is not None:

                def _remove(
                    entries: list[dict[str, Any]], existing_key: str = key
                ) -> list[dict[str, Any]]:
                    return [entry for entry in entries if entry["pk"] != existing_key]

                await self._rewrite_index_bucket(
                    client,
                    index_name=index_name,
                    partition_key=old_partition,
                    mutator=_remove,
                )

            if new_partition is not None:
                sort_value = (
                    _field_value(new_value, index.sort_key) if index.sort_key is not None else key
                )

                def _add(
                    entries: list[dict[str, Any]], key: str = key, sort_value: Any = sort_value
                ):
                    filtered = [entry for entry in entries if entry["pk"] != key]
                    filtered.append({"pk": key, "sort": sort_value})
                    return filtered

                await self._rewrite_index_bucket(
                    client,
                    index_name=index_name,
                    partition_key=new_partition,
                    mutator=_add,
                )

    async def connect(self) -> None:
        """Create a Redis client for the current event loop. Called lazily on first use."""
        await self._ensure_connected()

    async def _ensure_connected(self) -> Any:
        """Return the client for the running event loop, creating it if needed."""
        import redis.asyncio as aioredis

        loop = asyncio.get_running_loop()
        loop_id = id(loop)
        if loop_id not in self._clients:
            self._clients[loop_id] = aioredis.from_url(self.url, decode_responses=True)
        return self._clients[loop_id]

    async def get(self, key: str) -> Any | None:
        client = await self._ensure_connected()
        raw = await client.get(self._key(key))
        if raw is None:
            return None
        return json.loads(raw)

    async def set(self, key: str, value: Any, *, ttl: float | None = None) -> None:
        client = await self._ensure_connected()
        full_key = self._key(key)
        raw_old = await client.get(full_key)
        old_value = json.loads(raw_old) if raw_old is not None else None
        pipe = client.pipeline(transaction=True)
        ttl_px = self._ttl_px(ttl)
        if ttl_px is None:
            pipe.set(full_key, json.dumps(value))
        else:
            pipe.set(full_key, json.dumps(value), px=ttl_px)
        pipe.zadd(self._key_index(), {key: 0})
        await pipe.execute()
        await self._sync_indexes(client, key, old_value, value)

    async def delete(self, key: str) -> None:
        client = await self._ensure_connected()
        full_key = self._key(key)
        raw_old = await client.get(full_key)
        old_value = json.loads(raw_old) if raw_old is not None else None
        pipe = client.pipeline(transaction=True)
        pipe.delete(full_key)
        pipe.zrem(self._key_index(), key)
        await pipe.execute()
        if old_value is not None:
            await self._sync_indexes(client, key, old_value, None)

    async def list(self) -> list[tuple[str, Any]]:
        client = await self._ensure_connected()
        await self._ensure_key_index(client)
        keys = await client.zrange(self._key_index(), 0, -1)
        if not keys:
            return []
        values = await client.mget(*[self._key(key) for key in keys])
        result = []
        stale_keys: list[str] = []
        for k, v in zip(keys, values):
            if v is not None:
                result.append((k, json.loads(v)))
            else:
                stale_keys.append(k)
        if stale_keys:
            await self._remove_stale_key_index_members(client, stale_keys)
        return result

    async def list_page(self, *, limit: int, cursor: str | None):
        client = await self._ensure_connected()
        await self._ensure_key_index(client)
        limit = _normalize_limit(limit)
        decoded = _validate_cursor(cursor, mode="list")
        last_key = decoded.get("last_key")
        min_value = f"({last_key}" if last_key is not None else "-"
        live_items = await self._collect_live_key_items(
            client,
            min_value=min_value,
            max_value="+",
            limit=limit,
        )
        items = live_items[:limit]
        has_more = len(live_items) > limit
        next_cursor = None
        if has_more and items:
            next_cursor = _encode_cursor({"mode": "list", "last_key": items[-1][0]})
        return Page(items=items, next_cursor=next_cursor, has_more=has_more)

    async def scan(self, prefix: str = "") -> List[tuple[str, Any]]:
        page = await self.scan_page(prefix=prefix, limit=10_000, cursor=None)
        items = list(page.items)
        while page.has_more:
            page = await self.scan_page(prefix=prefix, limit=10_000, cursor=page.next_cursor)
            items.extend(page.items)
        return items

    async def scan_page(self, prefix: str = "", *, limit: int, cursor: str | None):
        client = await self._ensure_connected()
        await self._ensure_key_index(client)
        limit = _normalize_limit(limit)
        decoded = _validate_cursor(cursor, mode="scan", extra={"prefix": prefix})
        if prefix:
            last_key = decoded.get("last_key")
            min_value = f"({last_key}" if last_key is not None else f"[{prefix}"
            max_value = f"[{prefix}\uffff"
            live_items = await self._collect_live_key_items(
                client,
                min_value=min_value,
                max_value=max_value,
                limit=limit,
            )
        else:
            return await self.list_page(limit=limit, cursor=cursor)

        items = live_items[:limit]
        has_more = len(live_items) > limit
        next_cursor = None
        if has_more and items:
            next_cursor = _encode_cursor(
                {"mode": "scan", "prefix": prefix, "last_key": items[-1][0]}
            )
        return Page(items=items, next_cursor=next_cursor, has_more=has_more)

    async def query_index(
        self,
        index_name: str,
        key: Any,
        *,
        limit: int,
        cursor: str | None,
    ):
        client = await self._ensure_connected()
        limit = _normalize_limit(limit)
        decoded = _validate_cursor(
            cursor,
            mode="index",
            extra={"index_name": index_name, "key": _cursor_identity(key)},
        )
        bucket_key = self._index_bucket_key(index_name, key)
        offset = int(decoded.get("offset", 0)) if decoded else 0
        raw_entries = await client.lrange(bucket_key, 0, -1)
        entries = [json.loads(entry) for entry in raw_entries]
        primary_keys = [entry["pk"] for entry in entries]
        values = (
            await client.mget(*[self._key(primary_key) for primary_key in primary_keys])
            if primary_keys
            else []
        )
        stale_keys = {entry["pk"] for entry, value in zip(entries, values) if value is None}
        if stale_keys:
            await self._rewrite_index_bucket(
                client,
                index_name=index_name,
                partition_key=key,
                mutator=lambda bucket_entries: [
                    entry for entry in bucket_entries if entry["pk"] not in stale_keys
                ],
            )
            entries = [entry for entry in entries if entry["pk"] not in stale_keys]
            primary_keys = [entry["pk"] for entry in entries]
            values = (
                await client.mget(*[self._key(primary_key) for primary_key in primary_keys])
                if primary_keys
                else []
            )

        live_entries = [
            (entry, json.loads(value)) for entry, value in zip(entries, values) if value is not None
        ]
        page_entries = live_entries[offset : offset + limit]
        has_more = len(live_entries) > offset + limit
        items = [item for _, item in page_entries]
        next_cursor = None
        if has_more:
            next_cursor = _encode_cursor(
                {
                    "mode": "index",
                    "index_name": index_name,
                    "key": _cursor_identity(key),
                    "offset": offset + len(items),
                }
            )
        return Page(items=items, next_cursor=next_cursor, has_more=has_more)

    async def ensure_indexes(self) -> None:
        return None

    async def increment_counter(self, key: str, delta: int = 1) -> int:
        """Atomically increment a counter using Redis INCR."""
        client = await self._ensure_connected()
        new_value = await client.incrby(self._key(key), delta)
        await client.zadd(self._key_index(), {key: 0})
        return int(new_value)

    async def atomic_update(
        self,
        key: str,
        fn: Callable[[Any], Any],
        *,
        ttl: float | None = None,
        max_retries: int = 64,
    ) -> Any:
        """Atomically read, apply *fn*, and write back using a Redis pipeline with WATCH.

        Retries up to *max_retries* times on ``WatchError`` before surfacing
        a :class:`skaal.errors.SkaalConflict`.  Transient connection errors
        become :class:`skaal.errors.SkaalUnavailable`.
        """
        import redis.asyncio as aioredis
        from redis.exceptions import (
            ConnectionError as RedisConnectionError,
        )

        client = await self._ensure_connected()
        full_key = self._key(key)
        try:
            async with client.pipeline(transaction=True) as pipe:
                for _ in range(max_retries):
                    try:
                        await pipe.watch(full_key)
                        raw = await pipe.get(full_key)
                        current = json.loads(raw) if raw is not None else None
                        new_value = fn(current)
                        pipe.multi()
                        ttl_px = self._ttl_px(ttl)
                        if ttl_px is None:
                            pipe.set(full_key, json.dumps(new_value))
                        else:
                            pipe.set(full_key, json.dumps(new_value), px=ttl_px)
                        pipe.zadd(self._key_index(), {key: 0})
                        await pipe.execute()
                        await self._sync_indexes(client, key, current, new_value)
                        return new_value
                    except aioredis.WatchError:
                        continue
                raise SkaalConflict(
                    f"atomic_update on {key!r} lost {max_retries} consecutive races"
                )
        except RedisConnectionError as exc:
            raise SkaalUnavailable(f"Redis unavailable: {exc}") from exc

    async def close(self) -> None:
        for client in self._clients.values():
            await client.aclose()
        self._clients.clear()

    def __repr__(self) -> str:
        return f"RedisBackend(url={self.url!r}, namespace={self.namespace!r})"
