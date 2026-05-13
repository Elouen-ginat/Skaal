"""Skaal storage backends.

Each backend exists as a concrete implementation under `skaal.backends.*`.
The typed `Backend` token tree and the binding registry (ADR 028 §6.12)
land in Phase 3 — until then the only canonical lookup path is the lazy
`__getattr__` shim below.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

from skaal.backends.base import StorageBackend
from skaal.backends.local_backend import LocalMap

__all__ = [
    "DynamoBackend",
    "LocalMap",
    "PostgresBackend",
    "RedisBackend",
    "RedisStreamChannel",
    "SqliteBackend",
    "StorageBackend",
]


_LAZY_BACKENDS: dict[str, tuple[str, str]] = {
    "DynamoBackend": ("skaal.backends.dynamodb_backend", "DynamoBackend"),
    "FirestoreBackend": ("skaal.backends.firestore_backend", "FirestoreBackend"),
    "PostgresBackend": ("skaal.backends.postgres_backend", "PostgresBackend"),
    "RedisBackend": ("skaal.backends.redis_backend", "RedisBackend"),
    "SqliteBackend": ("skaal.backends.sqlite_backend", "SqliteBackend"),
    "RedisStreamChannel": ("skaal.backends.redis_channel", "RedisStreamChannel"),
    "S3BlobBackend": ("skaal.backends.s3_blob_backend", "S3BlobBackend"),
    "GCSBlobBackend": ("skaal.backends.gcs_blob_backend", "GCSBlobBackend"),
    "FileBlobBackend": ("skaal.backends.file_blob_backend", "FileBlobBackend"),
}


def __getattr__(name: str) -> Any:
    target = _LAZY_BACKENDS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = target
    module = import_module(module_name)
    return getattr(module, attr_name)
