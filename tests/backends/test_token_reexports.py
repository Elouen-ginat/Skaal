"""Tests for the per-backend public import paths (ADR 032 §4.5)."""

from __future__ import annotations

import importlib

import pytest

from skaal.backends._tokens import ALL_TOKENS

# Mapping from token class name to the Python module that publicly re-exports
# it (Python module names cannot contain hyphens, and `lambda` is reserved).
_REEXPORT_MODULE: dict[str, str] = {
    "Sqlite": "skaal.backends.sqlite",
    "Postgres": "skaal.backends.postgres",
    "Redis": "skaal.backends.redis",
    "DynamoDB": "skaal.backends.dynamodb",
    "Firestore": "skaal.backends.firestore",
    "S3": "skaal.backends.s3",
    "Gcs": "skaal.backends.gcs",
    "FilesystemBlob": "skaal.backends.filesystem_blob",
    "InProcessChannel": "skaal.backends.in_process_channel",
    "RedisChannel": "skaal.backends.redis_channel",
    "Sqs": "skaal.backends.sqs",
    "Pubsub": "skaal.backends.pubsub",
    "Asyncio": "skaal.backends.asyncio",
    "Lambda": "skaal.backends.lambda_",
    "CloudRun": "skaal.backends.cloud_run",
    "Uvicorn": "skaal.backends.uvicorn",
    "ApigwLambda": "skaal.backends.apigw_lambda",
    "Apscheduler": "skaal.backends.apscheduler",
    "EventBridgeLambda": "skaal.backends.eventbridge_lambda",
    "CloudSchedulerCloudRun": "skaal.backends.cloud_scheduler_run",
    "SqsLambdaWorker": "skaal.backends.sqs_lambda_worker",
    "CloudTasksCloudRun": "skaal.backends.cloud_tasks_run",
    "DotenvSecret": "skaal.backends.dotenv",
    "AwsSecretsManager": "skaal.backends.aws_secrets_manager",
    "GcpSecretManager": "skaal.backends.gcp_secret_manager",
    "BigQuery": "skaal.backends.bigquery",
}


def test_every_token_has_a_reexport_entry() -> None:
    token_names = {token.__name__ for token in ALL_TOKENS}
    assert token_names == set(_REEXPORT_MODULE.keys())


@pytest.mark.parametrize("class_name,module_name", sorted(_REEXPORT_MODULE.items()))
def test_reexport_module_resolves_to_token(class_name: str, module_name: str) -> None:
    module = importlib.import_module(module_name)
    assert hasattr(module, class_name), f"{module_name} missing {class_name}"
    reexported = getattr(module, class_name)
    canonical = getattr(importlib.import_module("skaal.backends._tokens"), class_name)
    assert reexported is canonical, (
        f"{module_name}.{class_name} is not the canonical token from _tokens"
    )


@pytest.mark.parametrize("module_name", sorted(_REEXPORT_MODULE.values()))
def test_reexport_module_declares_all(module_name: str) -> None:
    module = importlib.import_module(module_name)
    assert "__all__" in module.__dict__, f"{module_name} missing __all__"
