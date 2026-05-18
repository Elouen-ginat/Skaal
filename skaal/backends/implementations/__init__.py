"""Grouped concrete backend implementations.

New imports should target this subpackage directly.
"""

from skaal.backends.implementations.blob import (
    FileBlobBackend,
    FsspecBlobBackend,
    GCSBlobBackend,
    S3BlobBackend,
)
from skaal.backends.implementations.data import (
    BigQueryBackend,
    DynamoBackend,
    FirestoreBackend,
    PostgresBackend,
    RedisBackend,
    SqliteBackend,
)
from skaal.backends.implementations.local import LocalMap
from skaal.backends.implementations.messaging import RedisStreamChannel, SqsChannelBackend

__all__ = [
    "BigQueryBackend",
    "DynamoBackend",
    "FileBlobBackend",
    "FirestoreBackend",
    "FsspecBlobBackend",
    "GCSBlobBackend",
    "LocalMap",
    "PostgresBackend",
    "RedisBackend",
    "RedisStreamChannel",
    "S3BlobBackend",
    "SqliteBackend",
    "SqsChannelBackend",
]
