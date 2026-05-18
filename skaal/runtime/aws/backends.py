"""Backend factory helpers for the built-in AWS runtime target."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote_plus

from skaal.errors import RuntimeWiringError
from skaal.runtime._registry import RuntimeBackendFactoryContext


def build_dynamodb_store(context: RuntimeBackendFactoryContext) -> Any:
    from skaal.backends.dynamodb_backend import DynamoBackend

    binding = require_binding(context)
    env = require_env(context)
    [table_key] = binding.connection.env_var_keys
    table_name = require_env_var(env, table_key, binding.resource_id)
    region = env.get("AWS_REGION") or env.get("AWS_DEFAULT_REGION") or "us-east-1"
    return DynamoBackend(table_name=table_name, region=region)


def build_redis_store(context: RuntimeBackendFactoryContext) -> Any:
    from skaal.backends.redis_backend import RedisBackend

    binding = require_binding(context)
    env = require_env(context)
    [url_key] = binding.connection.env_var_keys
    url = require_env_var(env, url_key, binding.resource_id)
    return RedisBackend(url=url, namespace=context.target.__name__)


def build_s3_blob(context: RuntimeBackendFactoryContext) -> Any:
    from skaal.backends.s3_blob_backend import S3BlobBackend

    binding = require_binding(context)
    env = require_env(context)
    [bucket_key] = binding.connection.env_var_keys
    bucket = require_env_var(env, bucket_key, binding.resource_id)
    return S3BlobBackend(bucket=bucket, namespace=context.target.__name__)


def build_postgres_relational(context: RuntimeBackendFactoryContext) -> Any:
    from skaal.backends.postgres_backend import PostgresBackend

    binding = require_binding(context)
    env = require_env(context)
    host_key, secret_key = binding.connection.env_var_keys
    host = require_env_var(env, host_key, binding.resource_id)
    secret_arn = require_env_var(env, secret_key, binding.resource_id)
    region = aws_region(env)
    secret = load_secret_payload(secret_arn, region=region)
    username = require_secret_field(secret, "username", binding.resource_id)
    password = require_secret_field(secret, "password", binding.resource_id)
    port = int(secret.get("port", 5432))
    db_name = str(secret.get("dbname") or secret.get("db_name") or "skaal")
    dsn = f"postgresql://{quote_plus(username)}:{quote_plus(password)}@{host}:{port}/{db_name}"
    return PostgresBackend(dsn=dsn, namespace=context.target.__name__)


def build_redis_channel(context: RuntimeBackendFactoryContext) -> Any:
    from skaal.backends.redis_channel import RedisStreamChannel

    binding = require_binding(context)
    env = require_env(context)
    [url_key] = binding.connection.env_var_keys
    url = require_env_var(env, url_key, binding.resource_id)
    return RedisStreamChannel(url=url, namespace=context.target.__class__.__name__)


def build_sqs_channel(context: RuntimeBackendFactoryContext) -> Any:
    from skaal.backends.sqs_channel_backend import SqsChannelBackend

    binding = require_binding(context)
    env = require_env(context)
    [url_key] = binding.connection.env_var_keys
    queue_url = require_env_var(env, url_key, binding.resource_id)
    return SqsChannelBackend(queue_url=queue_url, region=aws_region(env))


def aws_region(env: Mapping[str, str]) -> str | None:
    return env.get("AWS_REGION") or env.get("AWS_DEFAULT_REGION")


def load_secret_payload(secret_arn: str, *, region: str | None) -> dict[str, Any]:
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeWiringError(
            "Postgres runtime wiring requires boto3 in the Lambda image."
        ) from exc

    client = boto3.client("secretsmanager", region_name=region)
    try:
        response = client.get_secret_value(SecretId=secret_arn)
    except Exception as exc:
        raise RuntimeWiringError(
            f"Failed to read Secrets Manager secret {secret_arn!r}: {exc}"
        ) from exc

    raw = response.get("SecretString")
    if not isinstance(raw, str):
        raise RuntimeWiringError(
            f"Secrets Manager secret {secret_arn!r} did not return a SecretString payload."
        )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeWiringError(
            f"Secrets Manager secret {secret_arn!r} did not contain valid JSON: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeWiringError(
            f"Secrets Manager secret {secret_arn!r} must decode to a JSON object."
        )
    return payload


def require_secret_field(payload: dict[str, Any], key: str, resource_id: str) -> str:
    value = payload.get(key)
    if isinstance(value, str) and value:
        return value
    raise RuntimeWiringError(
        f"Secrets Manager payload for resource {resource_id!r} is missing field {key!r}."
    )


def require_binding(context: RuntimeBackendFactoryContext) -> Any:
    binding = context.binding
    if binding is None:
        raise RuntimeWiringError(
            f"Runtime target {context.target_name!r} requires a runtime binding for "
            f"{context.resource_kind.value}/{context.backend_name}."
        )
    return binding


def require_env(context: RuntimeBackendFactoryContext) -> Mapping[str, str]:
    env = context.env
    if env is None:
        raise RuntimeWiringError(
            f"Runtime target {context.target_name!r} requires environment values for "
            f"{context.resource_kind.value}/{context.backend_name}."
        )
    return env


def require_env_var(env: Mapping[str, str], key: str, resource_id: str) -> str:
    value = env.get(key)
    if value:
        return value
    raise RuntimeWiringError(
        f"Missing required runtime env var {key!r} for resource {resource_id!r}."
    )


__all__ = [
    "aws_region",
    "build_dynamodb_store",
    "build_postgres_relational",
    "build_redis_channel",
    "build_redis_store",
    "build_s3_blob",
    "build_sqs_channel",
]
