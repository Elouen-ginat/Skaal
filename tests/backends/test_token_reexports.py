"""Tests for grouped backend token exports."""

from __future__ import annotations

import importlib

import pytest

from skaal.backends.tokens import ALL_TOKENS

_GROUPED_MODULE_EXPORTS: dict[str, set[str]] = {
    "skaal.backends.tokens.data": {
        "BigQuery",
        "DynamoDB",
        "Firestore",
        "Postgres",
        "Redis",
        "Sqlite",
    },
    "skaal.backends.tokens.blob": {"FilesystemBlob", "Gcs", "S3"},
    "skaal.backends.tokens.messaging": {"InProcessChannel", "Pubsub", "RedisChannel", "Sqs"},
    "skaal.backends.tokens.compute": {"ApigwLambda", "Asyncio", "CloudRun", "Lambda", "Uvicorn"},
    "skaal.backends.tokens.orchestration": {
        "Apscheduler",
        "CloudSchedulerCloudRun",
        "CloudTasksCloudRun",
        "EventBridgeLambda",
        "SqsLambdaWorker",
    },
    "skaal.backends.tokens.secrets": {
        "AwsSecretsManager",
        "DotenvSecret",
        "GcpSecretManager",
    },
}


def test_all_tokens_matches_grouped_package_exports() -> None:
    module = importlib.import_module("skaal.backends.tokens")
    token_names = {token.__name__ for token in ALL_TOKENS}
    assert token_names.issubset(set(module.__all__))


@pytest.mark.parametrize("module_name,class_names", sorted(_GROUPED_MODULE_EXPORTS.items()))
def test_grouped_token_module_exports(module_name: str, class_names: set[str]) -> None:
    module = importlib.import_module(module_name)
    assert set(module.__all__) == class_names
    canonical_module = importlib.import_module("skaal.backends.tokens")
    for class_name in class_names:
        assert getattr(module, class_name) is getattr(canonical_module, class_name)


def test_grouped_package_reexports_all_tokens() -> None:
    module = importlib.import_module("skaal.backends.tokens")
    token_names = {token.__name__ for token in ALL_TOKENS}
    assert token_names.issubset(set(module.__all__))
    for class_name in token_names:
        assert getattr(module, class_name) is getattr(
            importlib.import_module("skaal.backends.tokens"), class_name
        )
