"""Tests for AWS cold-start runtime wiring."""

from __future__ import annotations

import asyncio
import json
import sys

import pytest
from sqlmodel import Field

from skaal import App, BlobStore, Secret, Store, Table, Topic
from skaal.backends.tokens import Postgres, RedisChannel
from skaal.binding.model import Environment, LockFile, Target
from skaal.errors import RuntimeWiringError
from skaal.runtime.aws import wire_app_from_environment
from skaal.runtime.models import RuntimeBindingManifest
from skaal.table import get_backend


def _bound_and_manifest(app: App) -> tuple[object, RuntimeBindingManifest]:
    env = Environment(name="prod", target=Target.AWS, region="us-east-1")
    bound = app.plan(env, lock=LockFile())
    return bound, RuntimeBindingManifest.from_bound_plan(bound, env)


def test_wire_app_from_environment_wires_dynamodb_store() -> None:
    app = App("counter")

    @app.storage()
    class Counts(Store[int]):
        pass

    @app.expose()
    async def increment(name: str) -> dict[str, int]:
        value = await Counts.get(name) or 0
        await Counts.set(name, value + 1)
        return {"value": value + 1}

    _, manifest = _bound_and_manifest(app)
    [binding] = manifest.bindings
    [env_key] = binding.connection.env_var_keys

    wire_app_from_environment(
        app,
        manifest=manifest,
        env={env_key: "skaal-counter-table", "AWS_REGION": "us-west-2"},
    )

    backend = Counts._backend
    assert backend is not None
    assert backend.__class__.__name__ == "DynamoBackend"
    assert backend.table_name == "skaal-counter-table"
    assert backend.region == "us-west-2"


def test_wire_app_from_environment_requires_env_var() -> None:
    app = App("counter")

    @app.storage()
    class Counts(Store[int]):
        pass

    @app.expose()
    async def increment(name: str) -> dict[str, int]:
        value = await Counts.get(name) or 0
        await Counts.set(name, value + 1)
        return {"value": value + 1}

    _, manifest = _bound_and_manifest(app)

    with pytest.raises(RuntimeWiringError, match="Missing required runtime env var"):
        wire_app_from_environment(app, manifest=manifest, env={})


def test_wire_app_from_environment_wires_s3_blob() -> None:
    app = App("uploads")

    @app.storage(kind="blob")
    class Uploads(BlobStore):
        pass

    @app.expose()
    async def stat() -> dict[str, str]:
        return {"status": "ok"}

    _, manifest = _bound_and_manifest(app)
    [binding] = manifest.bindings
    [env_key] = binding.connection.env_var_keys

    wire_app_from_environment(app, manifest=manifest, env={env_key: "skaal-uploads-bucket"})

    backend = Uploads._backend
    assert backend is not None
    assert backend.__class__.__name__ == "S3BlobBackend"
    assert backend.bucket == "skaal-uploads-bucket"


def test_wire_app_from_environment_wires_postgres_relational(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = App("comments")

    @app.storage(kind="relational")
    class Comments(Table[Postgres], table=True):
        id: int | None = Field(default=None, primary_key=True)
        body: str

    @app.expose()
    async def list_comments() -> dict[str, str]:
        return {"status": "ok"}

    class _SecretsClient:
        def get_secret_value(self, *, SecretId: str) -> dict[str, str]:
            assert SecretId == "arn:aws:secretsmanager:eu-west-3:123:secret:rds"
            return {
                "SecretString": json.dumps(
                    {
                        "username": "skaal-user",
                        "password": "p@ss word",
                        "port": 5432,
                        "dbname": "skaal_db",
                    }
                )
            }

    class _Boto3Module:
        @staticmethod
        def client(service_name: str, region_name: str | None = None) -> _SecretsClient:
            assert service_name == "secretsmanager"
            assert region_name == "eu-west-3"
            return _SecretsClient()

    monkeypatch.setitem(__import__("sys").modules, "boto3", _Boto3Module())

    _, manifest = _bound_and_manifest(app)
    [binding] = manifest.bindings
    host_key, secret_key = binding.connection.env_var_keys

    wire_app_from_environment(
        app,
        manifest=manifest,
        env={
            host_key: "comments.cluster-123.eu-west-3.rds.amazonaws.com",
            secret_key: "arn:aws:secretsmanager:eu-west-3:123:secret:rds",
            "AWS_REGION": "eu-west-3",
        },
    )

    backend = get_backend(Comments)
    assert backend.__class__.__name__ == "PostgresBackend"
    assert backend.dsn == (
        "postgresql://skaal-user:p%40ss+word@"
        "comments.cluster-123.eu-west-3.rds.amazonaws.com:5432/skaal_db"
    )


@pytest.mark.asyncio
async def test_wire_app_from_environment_wires_redis_channel() -> None:
    app = App("events")

    @app.channel()
    class Events(Topic[dict, RedisChannel]):
        pass

    @app.expose()
    async def publish() -> dict[str, str]:
        return {"status": "ok"}

    _, manifest = _bound_and_manifest(app)
    [binding] = manifest.bindings
    [env_key] = binding.connection.env_var_keys

    wire_app_from_environment(
        app,
        manifest=manifest,
        env={env_key: "redis://cache.example:6379/0"},
    )

    channel = app.get_channel(Events)
    assert channel._wired is True
    assert channel._backend_name == "redis-channel"
    assert channel._backend.__class__.__name__ == "RedisStreamChannel"


@pytest.mark.asyncio
async def test_wire_app_from_environment_wires_sqs_channel(monkeypatch: pytest.MonkeyPatch) -> None:
    app = App("events")

    @app.channel()
    class Events(Topic[dict]):
        pass

    @app.expose()
    async def publish() -> dict[str, str]:
        return {"status": "ok"}

    sent: list[dict[str, str]] = []

    class _SqsClient:
        def send_message(self, *, QueueUrl: str, MessageBody: str) -> dict[str, str]:
            sent.append({"queue_url": QueueUrl, "body": MessageBody})
            return {"MessageId": "1"}

        def receive_message(self, **_: object) -> dict[str, list[dict[str, str]]]:
            return {"Messages": []}

        def delete_message(self, **_: object) -> None:
            return None

    class _Boto3Module:
        @staticmethod
        def client(service_name: str, region_name: str | None = None) -> _SqsClient:
            assert service_name == "sqs"
            assert region_name == "eu-west-3"
            return _SqsClient()

    monkeypatch.setitem(__import__("sys").modules, "boto3", _Boto3Module())

    _, manifest = _bound_and_manifest(app)
    [binding] = manifest.bindings
    [env_key] = binding.connection.env_var_keys

    wire_app_from_environment(
        app,
        manifest=manifest,
        env={env_key: "https://sqs.eu-west-3.amazonaws.com/123/events", "AWS_REGION": "eu-west-3"},
    )

    channel = app.get_channel(Events)
    await channel.send({"kind": "ping"})

    assert sent == [
        {
            "queue_url": "https://sqs.eu-west-3.amazonaws.com/123/events",
            "body": '{"kind": "ping"}',
        }
    ]


def test_wire_app_from_environment_wires_declared_aws_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = App("secrets")

    @app.expose(
        secrets=[
            Secret(
                "DB_DSN",
                provider="aws-secrets-manager",
                source="arn:aws:secretsmanager:eu-west-3:123:secret:db",
            )
        ]
    )
    async def query() -> dict[str, str]:
        return {"status": "ok"}

    class _SecretsClient:
        def get_secret_value(self, *, SecretId: str) -> dict[str, str]:
            assert SecretId == "arn:aws:secretsmanager:eu-west-3:123:secret:db"
            return {"SecretString": "postgresql://example/db"}

    class _Boto3Module:
        @staticmethod
        def client(service_name: str, region_name: str | None = None) -> _SecretsClient:
            assert service_name == "secretsmanager"
            assert region_name == "eu-west-3"
            return _SecretsClient()

    monkeypatch.setitem(sys.modules, "boto3", _Boto3Module())

    _, manifest = _bound_and_manifest(app)
    wire_app_from_environment(app, manifest=manifest, env={"AWS_REGION": "eu-west-3"})

    assert "DB_DSN" in app.secrets.specs
    assert asyncio.run(app.secrets.get("DB_DSN")) == "postgresql://example/db"


def test_wire_app_from_environment_requires_declared_env_secret() -> None:
    app = App("secrets")

    @app.expose(secrets=[Secret("API_TOKEN")])
    async def query() -> dict[str, str]:
        return {"status": "ok"}

    _, manifest = _bound_and_manifest(app)

    with pytest.raises(RuntimeWiringError, match="Failed to warm declared secrets"):
        wire_app_from_environment(app, manifest=manifest, env={})
