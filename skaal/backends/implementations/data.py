"""Data-oriented backend implementations."""

from __future__ import annotations

import asyncio
import base64
import builtins
import json
import math
import re
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import aiosqlite

from skaal.backends._native_types import (
    AsyncpgPoolProtocol,
    BigQueryClientProtocol,
    DynamoDbClientProtocol,
    FirestoreClientProtocol,
    RedisNativeClient,
    SqliteNativeClient,
)
from skaal.errors import SkaalBackendError, SkaalConflict, SkaalUnavailable
from skaal.serialization import decode_json_value
from skaal.storage import (
    _backend_index_fields,
    _cursor_identity,
    _encode_cursor,
    _field_value,
    _get_backend_indexes,
    _lex_sort_token,
    _normalize_limit,
    _validate_cursor,
)
from skaal.types.storage import CursorPayload, Page


def _decode_jsonb(raw: Any) -> Any:
    return decode_json_value(raw)


class SqliteBackend:
    """Persistent KV store backed by SQLite."""

    def __init__(
        self,
        path: str | Any = "skaal_local.db",
        namespace: str = "default",
    ) -> None:
        from pathlib import Path

        self.path = Path(path)
        self.namespace = namespace
        self._db: Any = None
        self._engine: Any = None
        self._session_factory: Any = None

    def _secondary_index_name(self, index_name: str) -> str:
        token = re.sub(r"[^0-9A-Za-z_]+", "_", f"{self.namespace}_{index_name}").strip("_")
        return f"skaal_kv_idx_{token or 'default'}"

    @staticmethod
    def _json_extract_expr(field_name: str) -> str:
        path = field_name.replace("'", "''")
        return f"json_extract(value, '$.{path}')"

    def _sqlalchemy_url(self) -> str:
        raw = str(self.path)
        if raw == ":memory:":
            return "sqlite+aiosqlite:///:memory:"
        return f"sqlite+aiosqlite:///{self.path.resolve().as_posix()}"

    async def connect(self) -> None:

        self._db = await aiosqlite.connect(self.path)
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS kv (
                key   TEXT NOT NULL,
                ns    TEXT NOT NULL DEFAULT '',
                value TEXT NOT NULL,
                expires_at REAL,
                PRIMARY KEY (ns, key)
            )
            """
        )
        await self._ensure_ttl_schema()
        await self._db.commit()
        await self.ensure_indexes()

    async def _ensure_ttl_schema(self) -> None:
        assert self._db is not None
        async with self._db.execute("PRAGMA table_info(kv)") as cursor:
            columns = {row[1] for row in await cursor.fetchall()}
        if "expires_at" not in columns:
            await self._db.execute("ALTER TABLE kv ADD COLUMN expires_at REAL")
        await self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_kv_ns_expires_at ON kv (ns, expires_at)"
        )

    def _expiry_deadline(self, ttl: float | None) -> float | None:
        if ttl is None:
            return None
        return time.time() + ttl

    async def _purge_expired(self) -> None:
        assert self._db is not None
        await self._db.execute(
            "DELETE FROM kv WHERE expires_at IS NOT NULL AND expires_at <= ?",
            (time.time(),),
        )

    async def _ensure_connected(self) -> None:
        if self._db is None:
            await self.connect()

    async def ensure_indexes(self) -> None:
        await self._ensure_connected()
        indexes = _get_backend_indexes(self)
        if not indexes:
            return
        for index in indexes.values():
            columns = ["ns", self._json_extract_expr(index.partition_key)]
            if index.sort_key is not None:
                columns.append(self._json_extract_expr(index.sort_key))
            columns.append("key")
            await self._db.execute(
                f'CREATE INDEX IF NOT EXISTS "{self._secondary_index_name(index.name)}" '
                f"ON kv ({', '.join(columns)})"
            )
        await self._db.commit()

    async def _ensure_relational_engine(self) -> None:
        if self._engine is not None:
            return

        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from sqlmodel.ext.asyncio.session import AsyncSession

        self._engine = create_async_engine(self._sqlalchemy_url())
        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def get(self, key: str) -> Any | None:
        await self._ensure_connected()
        async with self._db.execute(
            (
                "SELECT value FROM kv WHERE ns = ? AND key = ? "
                "AND (expires_at IS NULL OR expires_at > ?)"
            ),
            (self.namespace, key, time.time()),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    async def set(self, key: str, value: Any, *, ttl: float | None = None) -> None:
        await self._ensure_connected()
        await self._purge_expired()
        await self._db.execute(
            """
            INSERT INTO kv (ns, key, value, expires_at) VALUES (?, ?, ?, ?)
            ON CONFLICT (ns, key) DO UPDATE SET
                value = excluded.value,
                expires_at = excluded.expires_at
            """,
            (self.namespace, key, json.dumps(value), self._expiry_deadline(ttl)),
        )
        await self._db.commit()

    async def delete(self, key: str) -> None:
        await self._ensure_connected()
        await self._db.execute(
            "DELETE FROM kv WHERE ns = ? AND key = ?",
            (self.namespace, key),
        )
        await self._db.commit()

    async def list(self) -> list[tuple[str, Any]]:
        await self._ensure_connected()
        async with self._db.execute(
            (
                "SELECT key, value FROM kv WHERE ns = ? "
                "AND (expires_at IS NULL OR expires_at > ?) ORDER BY key"
            ),
            (self.namespace, time.time()),
        ) as cursor:
            rows = await cursor.fetchall()
        return [(row[0], json.loads(row[1])) for row in rows]

    async def list_page(self, *, limit: int, cursor: str | None):
        await self._ensure_connected()
        limit = _normalize_limit(limit)
        decoded = _validate_cursor(cursor, mode="list")
        last_key = decoded.get("last_key")
        query = "SELECT key, value FROM kv WHERE ns = ? AND (expires_at IS NULL OR expires_at > ?)"
        params: list[Any] = [self.namespace, time.time()]
        if last_key is not None:
            query += " AND key > ?"
            params.append(last_key)
        query += " ORDER BY key LIMIT ?"
        params.append(limit + 1)
        async with self._db.execute(query, tuple(params)) as sql_cursor:
            rows = await sql_cursor.fetchall()
        page_rows = rows[:limit]
        has_more = len(rows) > limit
        items = [(row[0], json.loads(row[1])) for row in page_rows]
        next_cursor = None
        if has_more and page_rows:
            next_cursor = _encode_cursor({"mode": "list", "last_key": page_rows[-1][0]})
        return Page(items=items, next_cursor=next_cursor, has_more=has_more)

    async def scan(self, prefix: str = "") -> builtins.list[tuple[str, Any]]:
        await self._ensure_connected()
        escaped_prefix = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        async with self._db.execute(
            (
                "SELECT key, value FROM kv WHERE ns = ? AND key LIKE ? ESCAPE '\\' "
                "AND (expires_at IS NULL OR expires_at > ?) ORDER BY key"
            ),
            (self.namespace, f"{escaped_prefix}%", time.time()),
        ) as cursor:
            rows = await cursor.fetchall()
        return [(row[0], json.loads(row[1])) for row in rows]

    async def scan_page(self, prefix: str = "", *, limit: int, cursor: str | None):
        await self._ensure_connected()
        limit = _normalize_limit(limit)
        decoded = _validate_cursor(cursor, mode="scan", extra={"prefix": prefix})
        last_key = decoded.get("last_key")
        escaped_prefix = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = (
            "SELECT key, value FROM kv WHERE ns = ? AND key LIKE ? ESCAPE '\\' "
            "AND (expires_at IS NULL OR expires_at > ?)"
        )
        params: list[Any] = [self.namespace, f"{escaped_prefix}%", time.time()]
        if last_key is not None:
            query += " AND key > ?"
            params.append(last_key)
        query += " ORDER BY key LIMIT ?"
        params.append(limit + 1)
        async with self._db.execute(query, tuple(params)) as sql_cursor:
            rows = await sql_cursor.fetchall()
        page_rows = rows[:limit]
        has_more = len(rows) > limit
        items = [(row[0], json.loads(row[1])) for row in page_rows]
        next_cursor = None
        if has_more and page_rows:
            next_cursor = _encode_cursor(
                {"mode": "scan", "prefix": prefix, "last_key": page_rows[-1][0]}
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
        await self._ensure_connected()
        await self.ensure_indexes()
        limit = _normalize_limit(limit)
        indexes = _get_backend_indexes(self)
        index = indexes.get(index_name)
        if index is None:
            raise ValueError(f"No secondary index named {index_name!r}")

        decoded = _validate_cursor(
            cursor,
            mode="index",
            extra={"index_name": index_name, "key": _cursor_identity(key)},
        )
        partition_path = f"$.{index.partition_key}"

        if index.sort_key is None:
            query = (
                "SELECT key, value FROM kv WHERE ns = ? AND json_extract(value, ?) = ? "
                "AND (expires_at IS NULL OR expires_at > ?)"
            )
            params: list[Any] = [self.namespace, partition_path, key, time.time()]
            last_key = decoded.get("last_key")
            if last_key is not None:
                query += " AND key > ?"
                params.append(last_key)
            query += " ORDER BY key LIMIT ?"
            params.append(limit + 1)
            async with self._db.execute(query, tuple(params)) as sql_cursor:
                rows = await sql_cursor.fetchall()
            page_rows = rows[:limit]
            has_more = len(rows) > limit
            items = [json.loads(row[1]) for row in page_rows]
            next_cursor = None
            if has_more and page_rows:
                next_cursor = _encode_cursor(
                    {
                        "mode": "index",
                        "index_name": index_name,
                        "key": _cursor_identity(key),
                        "last_key": page_rows[-1][0],
                    }
                )
            return Page(items=items, next_cursor=next_cursor, has_more=has_more)

        sort_path = f"$.{index.sort_key}"
        query = (
            "SELECT key, value, json_extract(value, ?) AS sort_value "
            "FROM kv WHERE ns = ? AND json_extract(value, ?) = ? "
            "AND (expires_at IS NULL OR expires_at > ?)"
        )
        params = [sort_path, self.namespace, partition_path, key, time.time()]
        if decoded.get("has_last_sort"):
            last_sort = decoded.get("last_sort")
            last_key = decoded.get("last_key")
            if last_sort is None:
                query += (
                    " AND (json_extract(value, ?) IS NOT NULL "
                    "OR (json_extract(value, ?) IS NULL AND key > ?))"
                )
                params.extend([sort_path, sort_path, last_key])
            else:
                query += (
                    " AND (json_extract(value, ?) > ? OR (json_extract(value, ?) = ? AND key > ?))"
                )
                params.extend([sort_path, last_sort, sort_path, last_sort, last_key])
        query += " ORDER BY sort_value, key LIMIT ?"
        params.append(limit + 1)
        async with self._db.execute(query, tuple(params)) as sql_cursor:
            rows = await sql_cursor.fetchall()
        page_rows = rows[:limit]
        has_more = len(rows) > limit
        items = [json.loads(row[1]) for row in page_rows]
        next_cursor = None
        if has_more and page_rows:
            next_cursor = _encode_cursor(
                {
                    "mode": "index",
                    "index_name": index_name,
                    "key": _cursor_identity(key),
                    "has_last_sort": True,
                    "last_sort": page_rows[-1][2],
                    "last_key": page_rows[-1][0],
                }
            )
        return Page(items=items, next_cursor=next_cursor, has_more=has_more)

    async def increment_counter(self, key: str, delta: int = 1) -> int:
        await self._ensure_connected()
        await self._db.execute("BEGIN IMMEDIATE")
        try:
            async with self._db.execute(
                "SELECT value FROM kv WHERE ns = ? AND key = ?",
                (self.namespace, key),
            ) as cursor:
                row = await cursor.fetchone()

            current = int(json.loads(row[0])) if row else 0
            new_value = current + delta

            await self._db.execute(
                """
                INSERT INTO kv (ns, key, value, expires_at) VALUES (?, ?, ?, NULL)
                ON CONFLICT (ns, key) DO UPDATE SET
                    value = excluded.value,
                    expires_at = excluded.expires_at
                """,
                (self.namespace, key, json.dumps(new_value)),
            )
            await self._db.commit()
            return new_value
        except Exception:
            await self._db.rollback()
            raise

    async def atomic_update(self, key: str, fn: Any, *, ttl: float | None = None) -> Any:
        await self._ensure_connected()
        await self._db.execute("BEGIN IMMEDIATE")
        try:
            async with self._db.execute(
                (
                    "SELECT value FROM kv WHERE ns = ? AND key = ? "
                    "AND (expires_at IS NULL OR expires_at > ?)"
                ),
                (self.namespace, key, time.time()),
            ) as cursor:
                row = await cursor.fetchone()
            current = json.loads(row[0]) if row else None
            updated = fn(current)
            await self._db.execute(
                """
                INSERT INTO kv (ns, key, value, expires_at) VALUES (?, ?, ?, ?)
                ON CONFLICT (ns, key) DO UPDATE SET
                    value = excluded.value,
                    expires_at = excluded.expires_at
                """,
                (self.namespace, key, json.dumps(updated), self._expiry_deadline(ttl)),
            )
            await self._db.commit()
            return updated
        except Exception:
            await self._db.rollback()
            raise

    async def ensure_relational_schema(self, model_cls: type) -> None:
        await self._ensure_relational_engine()
        typed_model = cast(Any, model_cls)
        async with self._engine.begin() as conn:
            await conn.run_sync(typed_model.metadata.create_all)

    async def relational_engine(self) -> Any:
        await self._ensure_relational_engine()
        return self._engine

    @asynccontextmanager
    async def open_relational_session(self, model_cls: type) -> AsyncIterator[Any]:
        await self.ensure_relational_schema(model_cls)
        assert self._session_factory is not None
        async with self._session_factory() as session:
            yield session

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None

    async def native(self) -> SqliteNativeClient:
        await self._ensure_connected()
        return cast(SqliteNativeClient, self._db)

    def __repr__(self) -> str:
        return f"SqliteBackend(path={self.path!r}, namespace={self.namespace!r})"


class PostgresBackend:
    def __init__(
        self,
        dsn: str,
        namespace: str = "default",
        min_size: int = 1,
        max_size: int = 10,
    ) -> None:
        self.dsn = dsn
        self.namespace = namespace
        self.min_size = min_size
        self.max_size = max_size
        self._pool: Any = None
        self._pool_loop: asyncio.AbstractEventLoop | None = None
        self._engine: Any = None
        self._session_factory: Any = None

    def _sqlalchemy_dsn(self) -> str:
        if self.dsn.startswith("postgresql+asyncpg://"):
            return self.dsn
        if self.dsn.startswith("postgresql://"):
            return "postgresql+asyncpg://" + self.dsn[len("postgresql://") :]
        if self.dsn.startswith("postgres://"):
            return "postgresql+asyncpg://" + self.dsn[len("postgres://") :]
        return self.dsn

    def _secondary_index_name(self, index_name: str) -> str:
        token = re.sub(r"[^0-9A-Za-z_]+", "_", f"{self.namespace}_{index_name}").strip("_")
        return f"skaal_kv_idx_{token or 'default'}"

    @staticmethod
    def _jsonb_path_expr(field_name: str) -> str:
        path = field_name.replace("\\", "\\\\").replace("'", "''")
        return f"(value #> '{{{path}}}')"

    async def connect(self) -> None:
        import asyncpg

        self._pool = await asyncpg.create_pool(
            self.dsn,
            min_size=self.min_size,
            max_size=self.max_size,
        )
        self._pool_loop = asyncio.get_running_loop()
        async with self._pool.acquire() as conn:
            try:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS skaal_kv (
                        ns    TEXT    NOT NULL DEFAULT '',
                        key   TEXT    NOT NULL,
                        value JSONB   NOT NULL,
                        expires_at TIMESTAMPTZ,
                        PRIMARY KEY (ns, key)
                    )
                    """
                )
                await conn.execute(
                    "ALTER TABLE skaal_kv ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ"
                )
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_skaal_kv_ns_expires_at ON skaal_kv (ns, expires_at)"
                )
            except asyncpg.exceptions.UniqueViolationError:
                pass
        await self.ensure_indexes()

    def _expiry_deadline(self, ttl: float | None) -> datetime | None:
        if ttl is None:
            return None
        return datetime.now(UTC) + timedelta(seconds=ttl)

    async def _ensure_connected(self) -> None:
        current_loop = asyncio.get_running_loop()
        if self._pool is not None and self._pool_loop is not current_loop:
            self._pool = None
            self._pool_loop = None
        if self._pool is None:
            await self.connect()

    async def ensure_indexes(self) -> None:
        await self._ensure_connected()
        indexes = _get_backend_indexes(self)
        if not indexes:
            return
        async with self._pool.acquire() as conn:
            for index in indexes.values():
                columns = ["ns", self._jsonb_path_expr(index.partition_key)]
                if index.sort_key is not None:
                    columns.append(self._jsonb_path_expr(index.sort_key))
                columns.append("key")
                await conn.execute(
                    f'CREATE INDEX IF NOT EXISTS "{self._secondary_index_name(index.name)}" '
                    f"ON skaal_kv ({', '.join(columns)})"
                )

    async def _ensure_relational_engine(self) -> None:
        if self._engine is not None:
            return

        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from sqlmodel.ext.asyncio.session import AsyncSession

        self._engine = create_async_engine(self._sqlalchemy_dsn())
        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def get(self, key: str) -> Any | None:
        await self._ensure_connected()
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                (
                    "SELECT value FROM skaal_kv WHERE ns = $1 AND key = $2 "
                    "AND (expires_at IS NULL OR expires_at > NOW())"
                ),
                self.namespace,
                key,
            )
        if row is None:
            return None
        raw = row["value"]
        if isinstance(raw, str):
            return json.loads(raw)
        return raw

    async def set(self, key: str, value: Any, *, ttl: float | None = None) -> None:
        await self._ensure_connected()
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO skaal_kv (ns, key, value, expires_at)
                VALUES ($1, $2, $3::jsonb, $4)
                ON CONFLICT (ns, key) DO UPDATE SET
                    value = excluded.value,
                    expires_at = excluded.expires_at
                """,
                self.namespace,
                key,
                json.dumps(value),
                self._expiry_deadline(ttl),
            )

    async def delete(self, key: str) -> None:
        await self._ensure_connected()
        async with self._pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM skaal_kv WHERE ns = $1 AND key = $2",
                self.namespace,
                key,
            )

    async def list(self) -> list[tuple[str, Any]]:
        await self._ensure_connected()
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                (
                    "SELECT key, value FROM skaal_kv WHERE ns = $1 "
                    "AND (expires_at IS NULL OR expires_at > NOW()) ORDER BY key"
                ),
                self.namespace,
            )
        return [(row["key"], _decode_jsonb(row["value"])) for row in rows]

    async def list_page(self, *, limit: int, cursor: str | None):
        await self._ensure_connected()
        limit = _normalize_limit(limit)
        decoded = _validate_cursor(cursor, mode="list")
        last_key = decoded.get("last_key")
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT key, value
                FROM skaal_kv
                WHERE ns = $1
                    AND (expires_at IS NULL OR expires_at > NOW())
                    AND ($2::text IS NULL OR key > $2)
                ORDER BY key
                LIMIT $3
                """,
                self.namespace,
                last_key,
                limit + 1,
            )
        page_rows = rows[:limit]
        has_more = len(rows) > limit
        items = [(row["key"], _decode_jsonb(row["value"])) for row in page_rows]
        next_cursor = None
        if has_more and page_rows:
            next_cursor = _encode_cursor({"mode": "list", "last_key": page_rows[-1]["key"]})
        return Page(items=items, next_cursor=next_cursor, has_more=has_more)

    async def scan(self, prefix: str = "") -> builtins.list[tuple[str, Any]]:
        await self._ensure_connected()
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                (
                    "SELECT key, value FROM skaal_kv WHERE ns = $1 AND key LIKE $2 "
                    "AND (expires_at IS NULL OR expires_at > NOW())"
                ),
                self.namespace,
                f"{prefix}%",
            )
        return [(row["key"], _decode_jsonb(row["value"])) for row in rows]

    async def scan_page(self, prefix: str = "", *, limit: int, cursor: str | None):
        await self._ensure_connected()
        limit = _normalize_limit(limit)
        decoded = _validate_cursor(cursor, mode="scan", extra={"prefix": prefix})
        last_key = decoded.get("last_key")
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT key, value
                FROM skaal_kv
                WHERE ns = $1
                    AND key LIKE $2
                    AND (expires_at IS NULL OR expires_at > NOW())
                    AND ($3::text IS NULL OR key > $3)
                ORDER BY key
                LIMIT $4
                """,
                self.namespace,
                f"{prefix}%",
                last_key,
                limit + 1,
            )
        page_rows = rows[:limit]
        has_more = len(rows) > limit
        items = [(row["key"], _decode_jsonb(row["value"])) for row in page_rows]
        next_cursor = None
        if has_more and page_rows:
            next_cursor = _encode_cursor(
                {"mode": "scan", "prefix": prefix, "last_key": page_rows[-1]["key"]}
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
        await self._ensure_connected()
        await self.ensure_indexes()
        limit = _normalize_limit(limit)
        indexes = _get_backend_indexes(self)
        index = indexes.get(index_name)
        if index is None:
            raise ValueError(f"No secondary index named {index_name!r}")

        decoded = _validate_cursor(
            cursor,
            mode="index",
            extra={"index_name": index_name, "key": _cursor_identity(key)},
        )
        partition_path = [index.partition_key]
        partition_value = json.dumps(key)

        if index.sort_key is None:
            last_key = decoded.get("last_key")
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT key, value
                    FROM skaal_kv
                    WHERE ns = $1
                      AND (value #> $2::text[]) = $3::jsonb
                      AND (expires_at IS NULL OR expires_at > NOW())
                      AND ($4::text IS NULL OR key > $4)
                    ORDER BY key
                    LIMIT $5
                    """,
                    self.namespace,
                    partition_path,
                    partition_value,
                    last_key,
                    limit + 1,
                )
            page_rows = rows[:limit]
            has_more = len(rows) > limit
            items = [_decode_jsonb(row["value"]) for row in page_rows]
            next_cursor = None
            if has_more and page_rows:
                next_cursor = _encode_cursor(
                    {
                        "mode": "index",
                        "index_name": index_name,
                        "key": _cursor_identity(key),
                        "last_key": page_rows[-1]["key"],
                    }
                )
            return Page(items=items, next_cursor=next_cursor, has_more=has_more)

        sort_path = [index.sort_key]
        if decoded.get("has_last_sort"):
            last_sort = json.dumps(decoded.get("last_sort"))
            last_key = decoded.get("last_key")
            query = """
                SELECT key, value, (value #> $4::text[]) AS sort_value
                FROM skaal_kv
                WHERE ns = $1
                  AND (value #> $2::text[]) = $3::jsonb
                  AND (expires_at IS NULL OR expires_at > NOW())
                  AND (
                    (value #> $4::text[]) > $5::jsonb
                    OR ((value #> $4::text[]) = $5::jsonb AND key > $6)
                  )
                ORDER BY sort_value, key
                LIMIT $7
            """
            params = [
                self.namespace,
                partition_path,
                partition_value,
                sort_path,
                last_sort,
                last_key,
                limit + 1,
            ]
        else:
            query = """
                SELECT key, value, (value #> $4::text[]) AS sort_value
                FROM skaal_kv
                WHERE ns = $1
                  AND (value #> $2::text[]) = $3::jsonb
                  AND (expires_at IS NULL OR expires_at > NOW())
                ORDER BY sort_value, key
                LIMIT $5
            """
            params = [self.namespace, partition_path, partition_value, sort_path, limit + 1]

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        page_rows = rows[:limit]
        has_more = len(rows) > limit
        items = [_decode_jsonb(row["value"]) for row in page_rows]
        next_cursor = None
        if has_more and page_rows:
            next_cursor = _encode_cursor(
                {
                    "mode": "index",
                    "index_name": index_name,
                    "key": _cursor_identity(key),
                    "has_last_sort": True,
                    "last_sort": _decode_jsonb(page_rows[-1]["sort_value"]),
                    "last_key": page_rows[-1]["key"],
                }
            )
        return Page(items=items, next_cursor=next_cursor, has_more=has_more)

    async def increment_counter(self, key: str, delta: int = 1) -> int:
        await self._ensure_connected()
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO skaal_kv (ns, key, value, expires_at)
                VALUES ($1, $2, to_jsonb($3::int), NULL)
                ON CONFLICT (ns, key)
                DO UPDATE SET
                    value = to_jsonb((skaal_kv.value::int + $3::int)),
                    expires_at = NULL
                RETURNING value
                """,
                self.namespace,
                key,
                delta,
            )
        if row:
            raw = row["value"]
            return int(json.loads(raw)) if isinstance(raw, str) else int(raw)
        return delta

    async def atomic_update(
        self,
        key: str,
        fn: Callable[[Any], Any],
        *,
        ttl: float | None = None,
    ) -> Any:
        import asyncpg

        await self._ensure_connected()
        try:
            async with self._pool.acquire() as conn, conn.transaction(isolation="serializable"):
                row = await conn.fetchrow(
                    (
                        "SELECT value FROM skaal_kv WHERE ns = $1 AND key = $2 "
                        "AND (expires_at IS NULL OR expires_at > NOW()) FOR UPDATE"
                    ),
                    self.namespace,
                    key,
                )
                raw = row["value"] if row is not None else None
                current = json.loads(raw) if isinstance(raw, str) else raw
                updated = fn(current)
                await conn.execute(
                    """
                    INSERT INTO skaal_kv (ns, key, value, expires_at)
                    VALUES ($1, $2, $3::jsonb, $4)
                    ON CONFLICT (ns, key) DO UPDATE SET
                        value = excluded.value,
                        expires_at = excluded.expires_at
                    """,
                    self.namespace,
                    key,
                    json.dumps(updated),
                    self._expiry_deadline(ttl),
                )
                return updated
        except asyncpg.exceptions.SerializationError as exc:
            raise SkaalConflict(f"atomic_update on {key!r} lost a race") from exc
        except (
            asyncpg.exceptions.ConnectionDoesNotExistError,
            asyncpg.exceptions.InterfaceError,
        ) as exc:
            raise SkaalUnavailable(f"Postgres unavailable: {exc}") from exc

    async def ensure_relational_schema(self, model_cls: type) -> None:
        await self._ensure_relational_engine()
        typed_model = cast(Any, model_cls)
        async with self._engine.begin() as conn:
            await conn.run_sync(typed_model.metadata.create_all)

    async def relational_engine(self) -> Any:
        await self._ensure_relational_engine()
        return self._engine

    @asynccontextmanager
    async def open_relational_session(self, model_cls: type) -> AsyncIterator[Any]:
        await self.ensure_relational_schema(model_cls)
        assert self._session_factory is not None
        async with self._session_factory() as session:
            yield session

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            self._pool_loop = None
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None

    async def native(self) -> AsyncpgPoolProtocol:
        await self._ensure_connected()
        return cast(AsyncpgPoolProtocol, self._pool)

    def __repr__(self) -> str:
        return f"PostgresBackend(dsn={self.dsn!r}, namespace={self.namespace!r})"


class RedisBackend:
    def __init__(self, url: str = "redis://localhost:6379", namespace: str = "default") -> None:
        self.url = url
        self.namespace = namespace
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

    def _index_sorted_set_key(self, index_name: str, partition_key: Any) -> str:
        token = base64.urlsafe_b64encode(
            json.dumps(partition_key, sort_keys=True, default=str).encode("utf-8")
        ).decode("ascii")
        return f"skaal:{self.namespace}:__idxz__:{index_name}:{token}"

    @staticmethod
    def _index_member(primary_key: str, sort_value: Any, *, has_sort_key: bool) -> str:
        if not has_sort_key:
            return primary_key
        return f"{_lex_sort_token(sort_value)}\x1f{primary_key}"

    @staticmethod
    def _member_primary_key(member: str) -> str:
        if "\x1f" not in member:
            return member
        return member.split("\x1f", 1)[1]

    def _ttl_px(self, ttl: float | None) -> int | None:
        if ttl is None:
            return None
        return max(1, math.ceil(ttl * 1000))

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
            await client.zadd(self._key_index(), dict.fromkeys(keys, 0))

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
            for key, value in zip(keys, values, strict=True):
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
                old_sort = (
                    _field_value(old_value, index.sort_key) if index.sort_key is not None else key
                )
                await client.zrem(
                    self._index_sorted_set_key(index_name, old_partition),
                    self._index_member(
                        key,
                        old_sort,
                        has_sort_key=index.sort_key is not None,
                    ),
                )

            if new_partition is not None:
                sort_value = (
                    _field_value(new_value, index.sort_key) if index.sort_key is not None else key
                )
                await client.zadd(
                    self._index_sorted_set_key(index_name, new_partition),
                    {
                        self._index_member(
                            key,
                            sort_value,
                            has_sort_key=index.sort_key is not None,
                        ): 0
                    },
                )

    async def connect(self) -> None:
        await self._ensure_connected()

    async def _ensure_connected(self) -> Any:
        import redis.asyncio as aioredis

        loop = asyncio.get_running_loop()
        loop_id = id(loop)
        if loop_id not in self._clients:
            self._clients[loop_id] = aioredis.from_url(  # type: ignore[no-untyped-call]
                self.url, decode_responses=True
            )
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
        result: list[tuple[str, Any]] = []
        stale_keys: list[str] = []
        for k, v in zip(keys, values, strict=True):
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

    async def scan(self, prefix: str = "") -> builtins.list[tuple[str, Any]]:
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
        indexes = _get_backend_indexes(self)
        index = indexes.get(index_name)
        if index is None:
            raise ValueError(f"No secondary index named {index_name!r}")
        decoded = _validate_cursor(
            cursor,
            mode="index",
            extra={"index_name": index_name, "key": _cursor_identity(key)},
        )
        if decoded.get("offset") is not None:
            raise ValueError("Invalid cursor")
        return await self._query_index_native(
            client,
            index_name=index_name,
            key=key,
            limit=limit,
            decoded=decoded,
        )

    async def _query_index_native(
        self,
        client: Any,
        *,
        index_name: str,
        key: Any,
        limit: int,
        decoded: CursorPayload,
    ) -> Page[Any]:
        collected: list[tuple[str, Any]] = []
        last_member = decoded.get("last_member")
        cursor = f"({last_member}" if last_member else "-"
        fetch_size = max(limit * 2, 50)
        sorted_set_key = self._index_sorted_set_key(index_name, key)

        while len(collected) < limit + 1:
            members = await client.zrangebylex(sorted_set_key, cursor, "+", start=0, num=fetch_size)
            if not members:
                break
            primary_keys = [self._member_primary_key(member) for member in members]
            values = await client.mget(*[self._key(primary_key) for primary_key in primary_keys])
            stale_members: list[str] = []
            for member, value in zip(members, values, strict=True):
                if value is None:
                    stale_members.append(member)
                    continue
                collected.append((member, json.loads(value)))
                if len(collected) >= limit + 1:
                    break
            for stale_member in stale_members:
                await client.zrem(sorted_set_key, stale_member)
            if len(members) < fetch_size or len(collected) >= limit + 1:
                break
            cursor = f"({members[-1]}"

        page_entries = collected[:limit]
        has_more = len(collected) > limit
        next_cursor = None
        if has_more and page_entries:
            next_cursor = _encode_cursor(
                {
                    "backend": "redis",
                    "mode": "index",
                    "index_name": index_name,
                    "key": _cursor_identity(key),
                    "last_member": page_entries[-1][0],
                }
            )
        return Page(
            items=[item for _, item in page_entries],
            next_cursor=next_cursor,
            has_more=has_more,
        )

    async def ensure_indexes(self) -> None:
        return None

    async def increment_counter(self, key: str, delta: int = 1) -> int:
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
        import redis.asyncio as aioredis
        from redis.exceptions import ConnectionError as RedisConnectionError

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

    async def native(self) -> RedisNativeClient:
        return await self._ensure_connected()

    def __repr__(self) -> str:
        return f"RedisBackend(url={self.url!r}, namespace={self.namespace!r})"


class DynamoBackend:
    def __init__(self, table_name: str, region: str = "us-east-1") -> None:
        self.table_name = table_name
        self.region = region
        self._client: Any | None = None

    def _get_client(self) -> DynamoDbClientProtocol:
        if self._client is None:
            try:
                import boto3
            except ImportError as exc:
                raise ImportError(
                    "boto3 is required for DynamoBackend. Install it with: pip install boto3"
                ) from exc
            self._client = boto3.client("dynamodb", region_name=self.region)
        return self._client

    def _secondary_index_name(self, index_name: str) -> str:
        token = re.sub(r"[^0-9A-Za-z_]+", "_", index_name).strip("_")
        return f"skaal_idx_{token or 'default'}"

    @staticmethod
    def _index_partition_value(value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)

    def _project_index_attributes(self, value: Any) -> dict[str, dict[str, str]]:
        projected: dict[str, dict[str, str]] = {}
        if value is None:
            return projected
        for index in _get_backend_indexes(self).values():
            fields = _backend_index_fields(index)
            partition_value = _field_value(value, index.partition_key)
            if partition_value is None:
                continue
            projected[fields.partition_field] = {"S": self._index_partition_value(partition_value)}
            if fields.sort_field is not None and index.sort_key is not None:
                projected[fields.sort_field] = {
                    "S": _lex_sort_token(_field_value(value, index.sort_key))
                }
        return projected

    def _index_resume_key(self, item: dict[str, Any], index: Any) -> dict[str, Any]:
        fields = _backend_index_fields(index)
        resume_key = {"pk": item["pk"]}
        if fields.partition_field in item:
            resume_key[fields.partition_field] = item[fields.partition_field]
        if fields.sort_field is not None and fields.sort_field in item:
            resume_key[fields.sort_field] = item[fields.sort_field]
        return resume_key

    def _ttl_attribute(self, ttl: float | None) -> dict[str, str] | None:
        if ttl is None:
            return None
        return {"N": str(int(time.time() + ttl))}

    def _is_expired_item(self, item: dict[str, Any] | None) -> bool:
        if item is None:
            return False
        expires_at = item.get("expires_at", {}).get("N")
        return expires_at is not None and float(expires_at) <= time.time()

    async def _run(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))

    async def get(self, key: str) -> Any | None:
        client = self._get_client()

        def _get() -> Any | None:
            resp = client.get_item(
                TableName=self.table_name,
                Key={"pk": {"S": key}},
            )
            item = resp.get("Item")
            if item is None:
                return None
            if self._is_expired_item(item):
                return None
            return json.loads(item["value"]["S"])

        return await self._run(_get)

    async def set(self, key: str, value: Any, *, ttl: float | None = None) -> None:
        client = self._get_client()

        def _put() -> None:
            item = {
                "pk": {"S": key},
                "kind": {"S": "item"},
                "value": {"S": json.dumps(value)},
            }
            item.update(self._project_index_attributes(value))
            expires_at = self._ttl_attribute(ttl)
            if expires_at is not None:
                item["expires_at"] = expires_at
            client.put_item(TableName=self.table_name, Item=item)

        await self._run(_put)

    async def delete(self, key: str) -> None:
        client = self._get_client()

        def _del() -> None:
            client.delete_item(
                TableName=self.table_name,
                Key={"pk": {"S": key}},
            )

        await self._run(_del)

    async def list(self) -> list[tuple[str, Any]]:
        page = await self.list_page(limit=10_000, cursor=None)
        items = list(page.items)
        while page.has_more:
            page = await self.list_page(limit=10_000, cursor=page.next_cursor)
            items.extend(page.items)
        return items

    async def list_page(self, *, limit: int, cursor: str | None):
        return await self._scan_page_native(prefix=None, limit=limit, cursor=cursor, mode="list")

    async def scan(self, prefix: str = "") -> builtins.list[tuple[str, Any]]:
        page = await self.scan_page(prefix=prefix, limit=10_000, cursor=None)
        items = list(page.items)
        while page.has_more:
            page = await self.scan_page(prefix=prefix, limit=10_000, cursor=page.next_cursor)
            items.extend(page.items)
        return items

    async def scan_page(self, prefix: str = "", *, limit: int, cursor: str | None):
        return await self._scan_page_native(
            prefix=prefix,
            limit=limit,
            cursor=cursor,
            mode="scan",
        )

    async def _scan_page_native(
        self,
        *,
        prefix: str | None,
        limit: int,
        cursor: str | None,
        mode: str,
    ) -> Page[tuple[str, Any]]:
        client = self._get_client()
        limit = _normalize_limit(limit)
        extra = {"prefix": prefix or ""} if mode == "scan" else None
        decoded = _validate_cursor(cursor, mode=mode, extra=extra)

        def _page() -> Page[tuple[str, Any]]:
            collected: list[tuple[str, Any]] = []
            last_key = decoded.get("exclusive_start_key") if decoded else None
            while len(collected) < limit + 1:
                kwargs: dict[str, Any] = {
                    "TableName": self.table_name,
                    "Limit": limit + 1 - len(collected),
                    "FilterExpression": "(attribute_not_exists(#kind) OR #kind = :item)"
                    + (" AND begins_with(pk, :pfx)" if prefix else ""),
                    "ExpressionAttributeNames": {"#kind": "kind"},
                    "ExpressionAttributeValues": {":item": {"S": "item"}},
                }
                if prefix:
                    kwargs["ExpressionAttributeValues"][":pfx"] = {"S": prefix}
                if last_key is not None:
                    kwargs["ExclusiveStartKey"] = last_key
                resp = client.scan(**kwargs)
                for item in resp.get("Items", []):
                    if "value" not in item:
                        continue
                    if self._is_expired_item(item):
                        continue
                    collected.append((item["pk"]["S"], json.loads(item["value"]["S"])))
                    if len(collected) >= limit + 1:
                        break
                last_key = resp.get("LastEvaluatedKey")
                if not last_key:
                    break

            page_items = collected[:limit]
            has_more = len(collected) > limit or bool(last_key)
            next_cursor = None
            if has_more and last_key is not None:
                payload = {"mode": mode, "exclusive_start_key": last_key}
                if prefix is not None and mode == "scan":
                    payload["prefix"] = prefix
                next_cursor = _encode_cursor(payload)
            return Page(items=page_items, next_cursor=next_cursor, has_more=has_more)

        return await self._run(_page)

    async def query_index(
        self,
        index_name: str,
        key: Any,
        *,
        limit: int,
        cursor: str | None,
    ):
        client = self._get_client()
        limit = _normalize_limit(limit)
        decoded = _validate_cursor(
            cursor,
            mode="index",
            extra={"index_name": index_name, "key": _cursor_identity(key)},
        )
        indexes = _get_backend_indexes(self)
        index = indexes.get(index_name)
        if index is None:
            raise ValueError(f"No secondary index named {index_name!r}")
        if decoded.get("offset") is not None:
            raise ValueError("Invalid cursor")
        return await self._run(
            self._query_index_native, client, index, index_name, key, limit, decoded
        )

    def _query_index_native(
        self,
        client: Any,
        index: Any,
        index_name: str,
        key: Any,
        limit: int,
        decoded: CursorPayload,
    ) -> Page[Any]:
        collected: list[tuple[dict[str, Any], Any]] = []
        exclusive_start_key = decoded.get("exclusive_start_key") if decoded else None
        fields = _backend_index_fields(index)

        while len(collected) < limit + 1:
            kwargs: dict[str, Any] = {
                "TableName": self.table_name,
                "IndexName": self._secondary_index_name(index_name),
                "KeyConditionExpression": "#idx_pk = :idx_pk",
                "ExpressionAttributeNames": {"#idx_pk": fields.partition_field},
                "ExpressionAttributeValues": {":idx_pk": {"S": self._index_partition_value(key)}},
                "Limit": limit + 1 - len(collected),
                "ScanIndexForward": True,
            }
            if exclusive_start_key is not None:
                kwargs["ExclusiveStartKey"] = exclusive_start_key
            response = client.query(**kwargs)
            raw_items = response.get("Items", [])
            last_evaluated_key = response.get("LastEvaluatedKey")
            for item in raw_items:
                if item.get("kind", {}).get("S") not in (None, "item"):
                    continue
                if "value" not in item or self._is_expired_item(item):
                    continue
                collected.append((item, json.loads(item["value"]["S"])))
                if len(collected) >= limit + 1:
                    break
            if len(collected) >= limit + 1 or last_evaluated_key is None:
                break
            exclusive_start_key = last_evaluated_key

        page_entries = collected[:limit]
        has_more = len(collected) > limit
        next_cursor = None
        if has_more and page_entries:
            next_cursor = _encode_cursor(
                {
                    "backend": "dynamodb",
                    "mode": "index",
                    "index_name": index_name,
                    "key": _cursor_identity(key),
                    "exclusive_start_key": self._index_resume_key(page_entries[-1][0], index),
                }
            )
        return Page(
            items=[item for _, item in page_entries],
            next_cursor=next_cursor,
            has_more=has_more,
        )

    async def ensure_indexes(self) -> None:
        client = self._get_client()
        if not hasattr(client, "describe_table") or not hasattr(client, "update_table"):
            return None

        def _ensure() -> None:
            indexes = _get_backend_indexes(self)
            if not indexes:
                return None
            table = client.describe_table(TableName=self.table_name).get("Table", {})
            existing = {
                gsi.get("IndexName")
                for gsi in table.get("GlobalSecondaryIndexes", [])
                if gsi.get("IndexName")
            }
            defined = {
                attr.get("AttributeName")
                for attr in table.get("AttributeDefinitions", [])
                if attr.get("AttributeName")
            }
            staged = set(defined)
            attribute_definitions: list[dict[str, str]] = []
            pending_updates: list[dict[str, Any]] = []
            for index in indexes.values():
                fields = _backend_index_fields(index)
                native_index_name = self._secondary_index_name(index.name)
                if native_index_name in existing:
                    continue
                for attribute_name in (fields.partition_field, fields.sort_field):
                    if attribute_name is None or attribute_name in staged:
                        continue
                    staged.add(attribute_name)
                    attribute_definitions.append(
                        {"AttributeName": attribute_name, "AttributeType": "S"}
                    )
                key_schema = [{"AttributeName": fields.partition_field, "KeyType": "HASH"}]
                if fields.sort_field is not None:
                    key_schema.append({"AttributeName": fields.sort_field, "KeyType": "RANGE"})
                pending_updates.append(
                    {
                        "Create": {
                            "IndexName": native_index_name,
                            "KeySchema": key_schema,
                            "Projection": {"ProjectionType": "ALL"},
                            "ProvisionedThroughput": {
                                "ReadCapacityUnits": 5,
                                "WriteCapacityUnits": 5,
                            },
                        }
                    }
                )
            if pending_updates:
                client.update_table(
                    TableName=self.table_name,
                    AttributeDefinitions=attribute_definitions,
                    GlobalSecondaryIndexUpdates=pending_updates,
                )

        await self._run(_ensure)

    async def increment_counter(self, key: str, delta: int = 1) -> int:
        client = self._get_client()

        def _increment() -> int:
            resp = client.update_item(
                TableName=self.table_name,
                Key={"pk": {"S": key}},
                UpdateExpression="SET #v = if_not_exists(#v, :zero) + :d",
                ExpressionAttributeNames={"#v": "counter"},
                ExpressionAttributeValues={
                    ":zero": {"N": "0"},
                    ":d": {"N": str(delta)},
                },
                ReturnValues="ALL_NEW",
            )
            new_val = resp["Attributes"]["counter"]
            if isinstance(new_val, dict) and "N" in new_val:
                return int(new_val["N"])
            return int(new_val)

        return await self._run(_increment)

    async def atomic_update(
        self,
        key: str,
        fn: Callable[[Any], Any],
        *,
        ttl: float | None = None,
        max_retries: int = 8,
    ) -> Any:
        try:
            import botocore.exceptions
        except ImportError as exc:
            raise SkaalUnavailable("botocore is required for DynamoBackend") from exc

        client = self._get_client()

        def _once() -> tuple[bool, Any]:
            resp = client.get_item(
                TableName=self.table_name,
                Key={"pk": {"S": key}},
                ConsistentRead=True,
            )
            item = resp.get("Item")
            if item is None:
                current: Any = None
                current_ver = 0
            else:
                current = None if self._is_expired_item(item) else json.loads(item["value"]["S"])
                current_ver = int(item.get("ver", {}).get("N", "0"))

            updated = fn(current)
            next_ver = current_ver + 1
            item_payload = {
                "pk": {"S": key},
                "kind": {"S": "item"},
                "value": {"S": json.dumps(updated)},
                "ver": {"N": str(next_ver)},
            }
            item_payload.update(self._project_index_attributes(updated))
            expires_at = self._ttl_attribute(ttl)
            if expires_at is not None:
                item_payload["expires_at"] = expires_at

            try:
                if item is None:
                    client.put_item(
                        TableName=self.table_name,
                        Item=item_payload,
                        ConditionExpression="attribute_not_exists(pk)",
                    )
                else:
                    client.put_item(
                        TableName=self.table_name,
                        Item=item_payload,
                        ConditionExpression="ver = :cur",
                        ExpressionAttributeValues={":cur": {"N": str(current_ver)}},
                    )
            except botocore.exceptions.ClientError as client_exc:
                code = client_exc.response.get("Error", {}).get("Code", "")
                if code == "ConditionalCheckFailedException":
                    return False, None
                raise
            return True, updated

        async def _loop() -> Any:
            for _ in range(max_retries):
                try:
                    ok, updated = await self._run(_once)
                except botocore.exceptions.EndpointConnectionError as net_exc:
                    raise SkaalUnavailable(f"DynamoDB unreachable: {net_exc}") from net_exc
                if ok:
                    return updated
            raise SkaalConflict(f"atomic_update on {key!r} lost {max_retries} consecutive races")

        return await _loop()

    async def close(self) -> None:
        self._client = None

    async def native(self) -> DynamoDbClientProtocol:
        return self._get_client()

    def __repr__(self) -> str:
        return f"DynamoBackend(table={self.table_name!r}, region={self.region!r})"


class FirestoreBackend:
    def __init__(
        self,
        collection: str,
        project: str | None = None,
        database: str = "(default)",
    ) -> None:
        self.collection = collection
        self.project = project
        self.database = database
        self._client: Any | None = None

    def _get_client(self) -> FirestoreClientProtocol:
        if self._client is None:
            try:
                from google.cloud import firestore
            except ImportError as exc:
                raise ImportError(
                    "google-cloud-firestore is required for FirestoreBackend. "
                    "Install it with: pip install google-cloud-firestore"
                ) from exc
            kwargs: dict[str, Any] = {"database": self.database}
            if self.project is not None:
                kwargs["project"] = self.project
            self._client = firestore.Client(**kwargs)
        return self._client

    def _col(self) -> Any:
        return self._get_client().collection(self.collection)

    def _project_index_fields(self, value: Any) -> dict[str, Any]:
        projected: dict[str, Any] = {}
        if value is None:
            return projected
        for index in _get_backend_indexes(self).values():
            fields = _backend_index_fields(index)
            partition_value = _field_value(value, index.partition_key)
            if partition_value is None:
                continue
            projected[fields.partition_field] = partition_value
            if fields.sort_field is not None and index.sort_key is not None:
                projected[fields.sort_field] = _field_value(value, index.sort_key)
        return projected

    @staticmethod
    def _resume_values(doc: Any, order_fields: list[str]) -> list[Any]:
        data = doc.to_dict() or {}
        return [doc.id if field == "pk" else data.get(field) for field in order_fields]

    def _bounded_live_query(
        self,
        build_query: Callable[[], Any],
        *,
        order_fields: list[str],
        limit: int,
        start_after: list[Any] | None,
    ) -> tuple[list[tuple[Any, dict[str, Any]]], bool, list[Any] | None]:
        collected: list[tuple[Any, dict[str, Any]]] = []
        current_start_after = start_after

        while len(collected) < limit + 1:
            query = build_query()
            if current_start_after is not None:
                query = query.start_after(current_start_after)
            batch_limit = limit + 1 - len(collected)
            docs = list(query.limit(batch_limit).stream())
            if not docs:
                break
            for doc in docs:
                data = doc.to_dict()
                if data is None or data.get("value") is None or self._is_expired_data(data):
                    continue
                collected.append((doc, data))
                if len(collected) >= limit + 1:
                    break
            if len(docs) < batch_limit or len(collected) >= limit + 1:
                break
            current_start_after = self._resume_values(docs[-1], order_fields)

        page_entries = collected[:limit]
        has_more = len(collected) > limit
        next_start_after = None
        if has_more and page_entries:
            next_start_after = self._resume_values(page_entries[-1][0], order_fields)
        return page_entries, has_more, next_start_after

    def _expiry_deadline(self, ttl: float | None) -> datetime | None:
        if ttl is None:
            return None
        return datetime.now(UTC) + timedelta(seconds=ttl)

    def _is_expired_data(self, data: dict[str, Any] | None) -> bool:
        if not data:
            return False
        expires_at = data.get("expires_at")
        if expires_at is None:
            return False
        return expires_at <= datetime.now(UTC)

    async def _run(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))

    async def get(self, key: str) -> Any | None:
        def _get() -> Any | None:
            doc = self._col().document(key).get()
            if not doc.exists:
                return None
            data = doc.to_dict()
            if self._is_expired_data(data):
                return None
            return json.loads(doc.get("value"))

        return await self._run(_get)

    async def set(self, key: str, value: Any, *, ttl: float | None = None) -> None:
        def _set() -> None:
            payload = {
                "pk": key,
                "value": json.dumps(value),
                "expires_at": self._expiry_deadline(ttl),
            }
            payload.update(self._project_index_fields(value))
            self._col().document(key).set(payload)

        await self._run(_set)

    async def delete(self, key: str) -> None:
        def _del() -> None:
            self._col().document(key).delete()

        await self._run(_del)

    async def list(self) -> list[tuple[str, Any]]:
        page = await self.list_page(limit=10_000, cursor=None)
        items = list(page.items)
        while page.has_more:
            page = await self.list_page(limit=10_000, cursor=page.next_cursor)
            items.extend(page.items)
        return items

    async def list_page(self, *, limit: int, cursor: str | None):
        limit = _normalize_limit(limit)
        decoded = _validate_cursor(cursor, mode="list")

        def _list_page() -> Page[tuple[str, Any]]:
            start_after = decoded.get("start_after")
            if start_after is None and decoded.get("last_key") is not None:
                start_after = [decoded["last_key"]]
            page_docs, has_more, next_start_after = self._bounded_live_query(
                lambda: self._col().order_by("pk"),
                order_fields=["pk"],
                limit=limit,
                start_after=start_after,
            )
            items = []
            for doc, data in page_docs:
                if data and "value" in data:
                    items.append((doc.id, json.loads(data["value"])))
            next_cursor = None
            if has_more and page_docs:
                next_cursor = _encode_cursor(
                    {
                        "backend": "firestore",
                        "mode": "list",
                        "last_key": page_docs[-1][0].id,
                        "start_after": next_start_after,
                    }
                )
            return Page(items=items, next_cursor=next_cursor, has_more=has_more)

        return await self._run(_list_page)

    async def scan(self, prefix: str = "") -> builtins.list[tuple[str, Any]]:
        page = await self.scan_page(prefix=prefix, limit=10_000, cursor=None)
        items = list(page.items)
        while page.has_more:
            page = await self.scan_page(prefix=prefix, limit=10_000, cursor=page.next_cursor)
            items.extend(page.items)
        return items

    async def scan_page(self, prefix: str = "", *, limit: int, cursor: str | None):
        limit = _normalize_limit(limit)
        decoded = _validate_cursor(cursor, mode="scan", extra={"prefix": prefix})

        def _scan_page() -> Page[tuple[str, Any]]:
            start_after = decoded.get("start_after")
            if start_after is None and decoded.get("last_key") is not None:
                start_after = [decoded["last_key"]]

            def _build_query() -> Any:
                query = self._col().order_by("pk")
                if prefix:
                    query = query.where("pk", ">=", prefix).where("pk", "<", prefix + "\uffff")
                return query

            page_docs, has_more, next_start_after = self._bounded_live_query(
                _build_query,
                order_fields=["pk"],
                limit=limit,
                start_after=start_after,
            )
            items = []
            for doc, data in page_docs:
                if data and "value" in data:
                    items.append((doc.id, json.loads(data["value"])))
            next_cursor = None
            if has_more and page_docs:
                next_cursor = _encode_cursor(
                    {
                        "backend": "firestore",
                        "mode": "scan",
                        "prefix": prefix,
                        "last_key": page_docs[-1][0].id,
                        "start_after": next_start_after,
                    }
                )
            return Page(items=items, next_cursor=next_cursor, has_more=has_more)

        return await self._run(_scan_page)

    async def query_index(
        self,
        index_name: str,
        key: Any,
        *,
        limit: int,
        cursor: str | None,
    ):
        limit = _normalize_limit(limit)
        indexes = _get_backend_indexes(self)
        index = indexes.get(index_name)
        if index is None:
            raise ValueError(f"No secondary index named {index_name!r}")
        decoded = _validate_cursor(
            cursor,
            mode="index",
            extra={"index_name": index_name, "key": _cursor_identity(key)},
        )
        if decoded.get("offset") is not None:
            raise ValueError("Invalid cursor")

        def _query_index() -> Page[Any]:
            fields = _backend_index_fields(index)
            if index.sort_key is None:
                start_after = decoded.get("start_after")
                if start_after is None and decoded.get("last_key") is not None:
                    start_after = [decoded["last_key"]]
                page_docs, has_more, next_start_after = self._bounded_live_query(
                    lambda: self._col().where(fields.partition_field, "==", key).order_by("pk"),
                    order_fields=["pk"],
                    limit=limit,
                    start_after=start_after,
                )
                items = [json.loads(data["value"]) for _, data in page_docs]
                next_cursor = None
                if has_more and page_docs:
                    next_cursor = _encode_cursor(
                        {
                            "backend": "firestore",
                            "mode": "index",
                            "index_name": index_name,
                            "key": _cursor_identity(key),
                            "last_key": page_docs[-1][0].id,
                            "start_after": next_start_after,
                        }
                    )
                return Page(items=items, next_cursor=next_cursor, has_more=has_more)

            start_after = decoded.get("start_after")
            if start_after is None and decoded.get("has_last_sort"):
                start_after = [decoded.get("last_sort"), decoded.get("last_key")]
            sort_field = fields.sort_field
            if sort_field is None:
                raise ValueError(f"Secondary index {index_name!r} requires a sort field")
            try:
                page_docs, has_more, next_start_after = self._bounded_live_query(
                    lambda: (
                        self._col()
                        .where(fields.partition_field, "==", key)
                        .order_by(sort_field)
                        .order_by("pk")
                    ),
                    order_fields=[sort_field, "pk"],
                    limit=limit,
                    start_after=start_after,
                )
            except Exception as exc:
                if type(exc).__name__ == "FailedPrecondition":
                    raise SkaalBackendError(
                        f"Firestore index required for secondary index {index_name!r}"
                    ) from exc
                raise
            items = [json.loads(data["value"]) for _, data in page_docs]
            next_cursor = None
            if has_more and page_docs:
                next_cursor = _encode_cursor(
                    {
                        "backend": "firestore",
                        "mode": "index",
                        "index_name": index_name,
                        "key": _cursor_identity(key),
                        "has_last_sort": True,
                        "last_sort": page_docs[-1][1].get(sort_field),
                        "last_key": page_docs[-1][0].id,
                        "start_after": next_start_after,
                    }
                )
            return Page(items=items, next_cursor=next_cursor, has_more=has_more)

        return await self._run(_query_index)

    async def ensure_indexes(self) -> None:
        return None

    async def increment_counter(self, key: str, delta: int = 1) -> int:
        def _increment() -> int:
            from google.cloud import firestore

            db = self._get_client()
            doc_ref = self._col().document(key)

            @firestore.transactional
            def _update_in_txn(txn: Any) -> int:
                doc = doc_ref.get(transaction=txn)
                current = json.loads(doc.get("value")) if doc.exists else 0
                new_value = int(current) + delta
                txn.set(doc_ref, {"pk": key, "value": json.dumps(new_value)})
                return new_value

            return _update_in_txn(db.transaction())

        return await self._run(_increment)

    async def atomic_update(
        self,
        key: str,
        fn: Callable[[Any], Any],
        *,
        ttl: float | None = None,
    ) -> Any:
        def _apply() -> Any:
            try:
                from google.api_core import exceptions as g_exc
                from google.cloud import firestore
            except ImportError as exc:
                raise SkaalUnavailable(
                    "google-cloud-firestore is required for atomic_update"
                ) from exc

            db = self._get_client()
            doc_ref = self._col().document(key)

            @firestore.transactional
            def _update_in_txn(txn: Any) -> Any:
                doc = doc_ref.get(transaction=txn)
                current_data = doc.to_dict() if doc.exists else None
                current = (
                    None
                    if self._is_expired_data(current_data)
                    else json.loads(doc.get("value"))
                    if doc.exists
                    else None
                )
                updated = fn(current)
                txn.set(
                    doc_ref,
                    {
                        "pk": key,
                        "value": json.dumps(updated),
                        "expires_at": self._expiry_deadline(ttl),
                        **self._project_index_fields(updated),
                    },
                )
                return updated

            try:
                return _update_in_txn(db.transaction())
            except g_exc.Aborted as exc:
                raise SkaalConflict(f"atomic_update on {key!r} lost a race") from exc
            except g_exc.ServiceUnavailable as exc:
                raise SkaalUnavailable(f"Firestore unavailable: {exc}") from exc

        return await self._run(_apply)

    async def close(self) -> None:
        self._client = None

    async def native(self) -> FirestoreClientProtocol:
        return self._get_client()

    def __repr__(self) -> str:
        return (
            f"FirestoreBackend(collection={self.collection!r}, "
            f"project={self.project!r}, database={self.database!r})"
        )


_SQLMODEL_TO_BIGQUERY: dict[str, str] = {
    "INTEGER": "INT64",
    "BIGINT": "INT64",
    "SMALLINT": "INT64",
    "FLOAT": "FLOAT64",
    "REAL": "FLOAT64",
    "DOUBLE": "FLOAT64",
    "NUMERIC": "NUMERIC",
    "BOOLEAN": "BOOL",
    "VARCHAR": "STRING",
    "TEXT": "STRING",
    "STRING": "STRING",
    "DATE": "DATE",
    "DATETIME": "DATETIME",
    "TIMESTAMP": "TIMESTAMP",
    "JSON": "JSON",
    "JSONB": "JSON",
}


def _bigquery_type_for(column: Any) -> str:
    raw = str(column.type).split("(")[0].upper().strip()
    return _SQLMODEL_TO_BIGQUERY.get(raw, "STRING")


class BigQueryBackend:
    def __init__(
        self,
        project: str,
        dataset: str,
        location: str = "US",
        table_prefix: str = "",
    ) -> None:
        self.project = project
        self.dataset = dataset
        self.location = location
        self.table_prefix = table_prefix
        self._client: Any | None = None

    def _get_client(self) -> BigQueryClientProtocol:
        if self._client is None:
            try:
                from google.cloud import bigquery
            except ImportError as exc:
                raise ImportError(
                    "google-cloud-bigquery is required for BigQueryBackend. "
                    "Install it with: pip install google-cloud-bigquery"
                ) from exc
            self._client = bigquery.Client(project=self.project)
        return self._client

    async def _run(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))

    async def native(self) -> BigQueryClientProtocol:
        return self._get_client()

    def _table_name(self, model_cls: type) -> str:
        raw = getattr(model_cls, "__tablename__", None) or model_cls.__name__.lower()
        return f"{self.table_prefix}{raw}"

    def _fully_qualified_table(self, model_cls: type) -> str:
        return f"{self.project}.{self.dataset}.{self._table_name(model_cls)}"

    async def ensure_relational_schema(self, model_cls: type) -> None:
        def _create() -> None:
            from google.cloud import bigquery

            client = self._get_client()
            typed_model = cast(Any, model_cls)
            dataset_id = f"{self.project}.{self.dataset}"
            dataset = bigquery.Dataset(dataset_id)
            dataset.location = self.location
            client.create_dataset(dataset, exists_ok=True)

            table_id = self._fully_qualified_table(model_cls)
            columns = list(typed_model.__table__.columns)
            schema = [
                bigquery.SchemaField(
                    column.name,
                    _bigquery_type_for(column),
                    mode="NULLABLE" if column.nullable else "REQUIRED",
                )
                for column in columns
            ]
            table = bigquery.Table(table_id, schema=schema)
            client.create_table(table, exists_ok=True)

        await self._run(_create)

    @asynccontextmanager
    async def open_relational_session(self, model_cls: type) -> AsyncIterator[Any]:
        await self.ensure_relational_schema(model_cls)
        raise NotImplementedError(
            "BigQuery does not support transactional sessions. "
            "Use `await <Model>.native()` to drive queries through the "
            "`google.cloud.bigquery.Client` directly."
        )
        if False:
            yield None

    async def close(self) -> None:
        self._client = None

    def __repr__(self) -> str:
        return (
            f"BigQueryBackend(project={self.project!r}, dataset={self.dataset!r}, "
            f"location={self.location!r})"
        )


__all__ = [
    "BigQueryBackend",
    "DynamoBackend",
    "FirestoreBackend",
    "PostgresBackend",
    "RedisBackend",
    "SqliteBackend",
]
