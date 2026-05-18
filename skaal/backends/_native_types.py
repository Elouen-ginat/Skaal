"""Typing helpers for backend-native client surfaces.

These aliases and protocols let backend tokens describe the concrete object
returned by `await <Primitive>.native()` without importing optional cloud SDKs
at type-check time. Base dependencies use their real runtime classes; optional
SDK-backed surfaces use local protocols that expose the operations Skaal sends
callers toward today.
"""

from __future__ import annotations

from typing import Any, Protocol, TypeAlias

import aiosqlite
from fsspec.spec import AbstractFileSystem
from redis.asyncio.client import Redis as RedisClient

SqliteNativeClient: TypeAlias = aiosqlite.Connection
RedisNativeClient: TypeAlias = RedisClient
BlobFilesystem: TypeAlias = AbstractFileSystem


class AsyncpgConnectionProtocol(Protocol):
    async def execute(self, query: str, *args: Any) -> Any: ...

    async def fetch(self, query: str, *args: Any) -> Any: ...

    async def fetchrow(self, query: str, *args: Any) -> Any: ...


class AsyncpgAcquireProtocol(Protocol):
    async def __aenter__(self) -> AsyncpgConnectionProtocol: ...

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None: ...


class AsyncpgPoolProtocol(Protocol):
    def acquire(self) -> AsyncpgAcquireProtocol: ...

    async def close(self) -> None: ...


class DynamoDbClientProtocol(Protocol):
    def get_item(self, **kwargs: Any) -> dict[str, Any]: ...

    def put_item(self, **kwargs: Any) -> dict[str, Any]: ...

    def delete_item(self, **kwargs: Any) -> dict[str, Any]: ...

    def update_item(self, **kwargs: Any) -> dict[str, Any]: ...

    def query(self, **kwargs: Any) -> dict[str, Any]: ...

    def scan(self, **kwargs: Any) -> dict[str, Any]: ...


class FirestoreClientProtocol(Protocol):
    def collection(self, path: str) -> Any: ...

    def batch(self) -> Any: ...

    def transaction(self) -> Any: ...

    def close(self) -> None: ...


class BigQueryJobProtocol(Protocol):
    def result(self) -> Any: ...


class BigQueryClientProtocol(Protocol):
    def create_dataset(self, dataset: Any, *, exists_ok: bool = False) -> Any: ...

    def create_table(self, table: Any, *, exists_ok: bool = False) -> Any: ...

    def insert_rows_json(self, table: str, rows: list[dict[str, Any]]) -> Any: ...

    def query(self, query: str, *args: Any, **kwargs: Any) -> BigQueryJobProtocol: ...


class SqsClientProtocol(Protocol):
    def send_message(self, **kwargs: Any) -> dict[str, Any]: ...

    def receive_message(self, **kwargs: Any) -> dict[str, Any]: ...

    def delete_message(self, **kwargs: Any) -> dict[str, Any]: ...


__all__ = [
    "AsyncpgConnectionProtocol",
    "AsyncpgPoolProtocol",
    "BigQueryClientProtocol",
    "BlobFilesystem",
    "DynamoDbClientProtocol",
    "FirestoreClientProtocol",
    "RedisNativeClient",
    "SqliteNativeClient",
    "SqsClientProtocol",
]
