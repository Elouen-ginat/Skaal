"""Skaal storage backends.

Two surfaces coexist in this package:

- **Backend tokens** (`Sqlite`, `Postgres`, `Redis`, …): typed class
  tokens consumed as the second generic parameter on the primitive
  classes (`Store[T, Redis]`). The canonical class lives in
  `skaal.backends._tokens`; each token is also re-exported from a thin
  module named after the token (`from skaal.backends.redis import
  Redis`) per ADR 032 §4.5.
- **Backend implementations** (`RedisBackend`, `PostgresBackend`, …):
  the concrete I/O classes the runtime adapters use. These continue to
  live in `<name>_backend.py` modules and are loaded lazily via the
  `__getattr__` shim below to avoid pulling in optional-extra SDKs at
  package import time.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

from skaal.backends.base import StorageBackend
from skaal.backends.local_backend import LocalMap

if TYPE_CHECKING:  # pragma: no cover - import-time-only stubs for pyright
    from skaal.backends.dynamodb_backend import DynamoBackend
    from skaal.backends.postgres_backend import PostgresBackend
    from skaal.backends.redis_backend import RedisBackend
    from skaal.backends.redis_channel import RedisStreamChannel
    from skaal.backends.sqlite_backend import SqliteBackend

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
