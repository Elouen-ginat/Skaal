"""Typed `Backend` token classes (ADR 028 §6.12, ADR 031 §3.2).

Each class in this module is a `Backend` subclass naming exactly one
backend the registry knows about. The classes are imported by the binding
layer (`skaal.binding.registry.REGISTRY`) and by user code (Phase 4) as the
second generic parameter on the primitive classes (`Store[User, Redis]`).

The classes carry no behaviour and no state — they exist for the type
system and for the registry. The `NativeClient` attribute is narrowed to
``object`` in Phase 3 to keep the registry import free of optional-extra
SDK dependencies; Phase 5 narrows it under ``TYPE_CHECKING`` so Pylance
sees the concrete SDK type on `.native()` calls.
"""

from __future__ import annotations

from typing import Any

from skaal.backends._base import Backend


class Sqlite(Backend[object]):
    name = "sqlite"
    kinds = frozenset({"store", "relational"})


class Postgres(Backend[object]):
    name = "postgres"
    kinds = frozenset({"relational"})


class Redis(Backend[object]):
    name = "redis"
    kinds = frozenset({"store", "channel"})


class DynamoDB(Backend[object]):
    name = "dynamodb"
    kinds = frozenset({"store"})


class Firestore(Backend[object]):
    name = "firestore"
    kinds = frozenset({"store"})


class S3(Backend[object]):
    name = "s3"
    kinds = frozenset({"blob"})


class Gcs(Backend[object]):
    name = "gcs"
    kinds = frozenset({"blob"})


class FilesystemBlob(Backend[object]):
    name = "filesystem-blob"
    kinds = frozenset({"blob"})


class InProcessChannel(Backend[object]):
    name = "in-process"
    kinds = frozenset({"channel"})


class RedisChannel(Backend[object]):
    name = "redis-channel"
    kinds = frozenset({"channel"})


class Sqs(Backend[object]):
    name = "sqs"
    kinds = frozenset({"channel"})


class Pubsub(Backend[object]):
    name = "pubsub"
    kinds = frozenset({"channel"})


class Asyncio(Backend[object]):
    name = "asyncio"
    kinds = frozenset({"function"})


class Lambda(Backend[object]):
    name = "lambda"
    kinds = frozenset({"function"})


class CloudRun(Backend[object]):
    name = "cloud-run"
    kinds = frozenset({"function", "asgi_service"})


class Uvicorn(Backend[object]):
    name = "uvicorn"
    kinds = frozenset({"asgi_service"})


class ApigwLambda(Backend[object]):
    name = "apigw-lambda"
    kinds = frozenset({"asgi_service"})


class Apscheduler(Backend[object]):
    name = "apscheduler"
    kinds = frozenset({"schedule", "job"})


class EventBridgeLambda(Backend[object]):
    name = "eventbridge-lambda"
    kinds = frozenset({"schedule"})


class CloudSchedulerCloudRun(Backend[object]):
    name = "cloud-scheduler-run"
    kinds = frozenset({"schedule"})


class SqsLambdaWorker(Backend[object]):
    name = "sqs-lambda-worker"
    kinds = frozenset({"job"})


class CloudTasksCloudRun(Backend[object]):
    name = "cloud-tasks-run"
    kinds = frozenset({"job"})


class DotenvSecret(Backend[object]):
    name = "dotenv"
    kinds = frozenset({"secret"})


class AwsSecretsManager(Backend[object]):
    name = "aws-secrets-manager"
    kinds = frozenset({"secret"})


class GcpSecretManager(Backend[object]):
    name = "gcp-secret-manager"
    kinds = frozenset({"secret"})


ALL_TOKENS: tuple[type[Backend[Any]], ...] = (
    Sqlite,
    Postgres,
    Redis,
    DynamoDB,
    Firestore,
    S3,
    Gcs,
    FilesystemBlob,
    InProcessChannel,
    RedisChannel,
    Sqs,
    Pubsub,
    Asyncio,
    Lambda,
    CloudRun,
    Uvicorn,
    ApigwLambda,
    Apscheduler,
    EventBridgeLambda,
    CloudSchedulerCloudRun,
    SqsLambdaWorker,
    CloudTasksCloudRun,
    DotenvSecret,
    AwsSecretsManager,
    GcpSecretManager,
)
