"""Grouped backend token exports.

This subpackage organizes typed backend tokens by their dominant role so the
`skaal.backends` package no longer needs one flat canonical token module.
"""

from skaal.backends.tokens.blob import S3, FilesystemBlob, Gcs
from skaal.backends.tokens.compute import ApigwLambda, Asyncio, CloudRun, Lambda, Uvicorn
from skaal.backends.tokens.data import BigQuery, DynamoDB, Firestore, Postgres, Redis, Sqlite
from skaal.backends.tokens.messaging import InProcessChannel, Pubsub, RedisChannel, Sqs
from skaal.backends.tokens.orchestration import (
    Apscheduler,
    CloudSchedulerCloudRun,
    CloudTasksCloudRun,
    EventBridgeLambda,
    SqsLambdaWorker,
)
from skaal.backends.tokens.secrets import AwsSecretsManager, DotenvSecret, GcpSecretManager

ALL_TOKENS = (
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
    BigQuery,
)

__all__ = [
    "ALL_TOKENS",
    "S3",
    "ApigwLambda",
    "Apscheduler",
    "Asyncio",
    "AwsSecretsManager",
    "BigQuery",
    "CloudRun",
    "CloudSchedulerCloudRun",
    "CloudTasksCloudRun",
    "DotenvSecret",
    "DynamoDB",
    "EventBridgeLambda",
    "FilesystemBlob",
    "Firestore",
    "GcpSecretManager",
    "Gcs",
    "InProcessChannel",
    "Lambda",
    "Postgres",
    "Pubsub",
    "Redis",
    "RedisChannel",
    "Sqlite",
    "Sqs",
    "SqsLambdaWorker",
    "Uvicorn",
]
