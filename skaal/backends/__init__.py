"""Skaal storage backends.

Two surfaces coexist in this package:

- **Backend tokens** (`Sqlite`, `Postgres`, `Redis`, …): typed class
        tokens consumed as the second generic parameter on the primitive
        classes (`Store[T, Redis]`). The canonical classes live under the
        grouped `skaal.backends.tokens` subpackage.
- **Backend implementations** (`RedisBackend`, `PostgresBackend`, …):
    the concrete I/O classes the runtime adapters use. Their canonical
    home is `skaal.backends.implementations`; selected classes are also
    loaded lazily from this package root via the `__getattr__` shim below
    to avoid pulling in optional-extra SDKs at package import time.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

from skaal.backends.base import StorageBackend
from skaal.backends.implementations.local import LocalMap

if TYPE_CHECKING:  # pragma: no cover - import-time-only stubs for pyright
    from skaal.backends.implementations.data import (
        DynamoBackend,
        PostgresBackend,
        RedisBackend,
        SqliteBackend,
    )
    from skaal.backends.implementations.messaging import RedisStreamChannel

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
    "BigQueryBackend": ("skaal.backends.implementations.data", "BigQueryBackend"),
    "DynamoBackend": ("skaal.backends.implementations.data", "DynamoBackend"),
    "FirestoreBackend": ("skaal.backends.implementations.data", "FirestoreBackend"),
    "PostgresBackend": ("skaal.backends.implementations.data", "PostgresBackend"),
    "RedisBackend": ("skaal.backends.implementations.data", "RedisBackend"),
    "SqliteBackend": ("skaal.backends.implementations.data", "SqliteBackend"),
    "RedisStreamChannel": ("skaal.backends.implementations.messaging", "RedisStreamChannel"),
    "S3BlobBackend": ("skaal.backends.implementations.blob", "S3BlobBackend"),
    "GCSBlobBackend": ("skaal.backends.implementations.blob", "GCSBlobBackend"),
    "FileBlobBackend": ("skaal.backends.implementations.blob", "FileBlobBackend"),
}


def __getattr__(name: str) -> Any:
    target = _LAZY_BACKENDS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = target
    module = import_module(module_name)
    return getattr(module, attr_name)
