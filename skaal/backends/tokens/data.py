"""Data-oriented backend tokens.

Tokens here primarily back stores or relational tables. Some also support
adjacent kinds; for example `Redis` also backs channels and `Sqlite` can host
relational resources.
"""

from skaal.backends._base import Backend
from skaal.backends._native_types import (
    AsyncpgPoolProtocol,
    BigQueryClientProtocol,
    DynamoDbClientProtocol,
    FirestoreClientProtocol,
    RedisNativeClient,
    SqliteNativeClient,
)


class Sqlite(Backend[SqliteNativeClient]):
    name = "sqlite"
    kinds = frozenset({"store", "relational"})
    NativeClient = SqliteNativeClient


class Postgres(Backend[AsyncpgPoolProtocol]):
    name = "postgres"
    kinds = frozenset({"relational"})
    NativeClient = AsyncpgPoolProtocol


class Redis(Backend[RedisNativeClient]):
    name = "redis"
    kinds = frozenset({"store", "channel"})
    NativeClient = RedisNativeClient


class DynamoDB(Backend[DynamoDbClientProtocol]):
    name = "dynamodb"
    kinds = frozenset({"store"})
    NativeClient = DynamoDbClientProtocol


class Firestore(Backend[FirestoreClientProtocol]):
    name = "firestore"
    kinds = frozenset({"store"})
    NativeClient = FirestoreClientProtocol


class BigQuery(Backend[BigQueryClientProtocol]):
    name = "bigquery"
    kinds = frozenset({"relational"})
    NativeClient = BigQueryClientProtocol


__all__ = ["BigQuery", "DynamoDB", "Firestore", "Postgres", "Redis", "Sqlite"]
