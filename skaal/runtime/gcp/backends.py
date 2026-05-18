"""Backend factory helpers for the built-in GCP runtime target (ADR 042)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Protocol, cast
from urllib.parse import quote_plus

from skaal.errors import RuntimeWiringError
from skaal.runtime._registry import RuntimeBackendFactoryContext


class GcpSecretPayload(Protocol):
    data: bytes


class GcpSecretVersionResponse(Protocol):
    payload: GcpSecretPayload


class GcpSecretManagerClient(Protocol):
    def access_secret_version(self, *, request: dict[str, str]) -> GcpSecretVersionResponse: ...


if TYPE_CHECKING:

    def _secretmanager_client() -> GcpSecretManagerClient: ...
else:

    def _secretmanager_client() -> GcpSecretManagerClient:
        from google.cloud import secretmanager

        return cast(GcpSecretManagerClient, secretmanager.SecretManagerServiceClient())


def build_firestore_store(context: RuntimeBackendFactoryContext) -> Any:
    """Build a `FirestoreBackend` from the GCP synth's emitted env vars.

    Skaal provisions one Firestore *database* per `Store` (named via the
    resource's deployment slug). Inside that database the store's records
    live in one fixed *collection* derived from the resource's bare name
    (e.g. ``examples.counter_api:Counts`` → ``Counts``). That keeps the
    client wiring symmetric with DynamoDB's "one resource → one table".
    """
    from skaal.backends.implementations.data import FirestoreBackend

    binding = require_binding(context)
    env = require_env(context)
    [database_key] = binding.connection.env_var_keys
    database = require_env_var(env, database_key, binding.resource_id)
    collection = binding.resource_id.rsplit(":", 1)[-1] or binding.resource_id
    project = env.get("GOOGLE_CLOUD_PROJECT") or env.get("GCP_PROJECT")
    return FirestoreBackend(collection=collection, project=project, database=database)


def build_gcs_blob(context: RuntimeBackendFactoryContext) -> Any:
    from skaal.backends.implementations.blob import GCSBlobBackend

    binding = require_binding(context)
    env = require_env(context)
    [bucket_key] = binding.connection.env_var_keys
    bucket = require_env_var(env, bucket_key, binding.resource_id)
    return GCSBlobBackend(bucket=bucket, namespace=context.target.__class__.__name__)


def build_pubsub_channel(context: RuntimeBackendFactoryContext) -> Any:
    from skaal.backends.implementations.messaging import SqsChannelBackend  # placeholder

    # Pub/Sub channel runtime backend lands behind the same protocol as the
    # SQS channel backend. The real Pub/Sub adapter is registered when the
    # `google-cloud-pubsub` SDK is installed; until then this raises so the
    # wiring surface is obvious instead of silently falling back to in-process.
    raise RuntimeWiringError(
        "Pub/Sub runtime backend is registered but no adapter is installed. "
        "Install `skaal[gcp]` and an implementation of `PubsubChannelBackend`."
    )
    if False:  # pragma: no cover - type narrowing for the linter
        SqsChannelBackend(queue_url="", region=None)


def build_postgres_relational(context: RuntimeBackendFactoryContext) -> Any:
    """Build a Postgres backend wired against Cloud SQL.

    The Cloud SQL synth emits two env vars per resource:
    ``SKAAL_DB_<slug>_CONN`` (the instance connection name) and
    ``SKAAL_DB_<slug>_SECRET`` (Secret Manager secret id holding the
    username/password/dbname JSON).
    """
    from skaal.backends.implementations.data import PostgresBackend

    binding = require_binding(context)
    env = require_env(context)
    conn_key, secret_key = binding.connection.env_var_keys
    conn_name = require_env_var(env, conn_key, binding.resource_id)
    secret_id = require_env_var(env, secret_key, binding.resource_id)
    project = env.get("GOOGLE_CLOUD_PROJECT") or env.get("GCP_PROJECT")
    payload = load_secret_payload(secret_id, project=project)
    username = require_secret_field(payload, "username", binding.resource_id)
    password = require_secret_field(payload, "password", binding.resource_id)
    db_name = str(payload.get("dbname") or payload.get("db_name") or "skaal")
    # Cloud Run uses Unix socket connections by default for Cloud SQL.
    socket_path = f"/cloudsql/{conn_name}"
    dsn = (
        f"postgresql://{quote_plus(username)}:{quote_plus(password)}@/{db_name}?host={socket_path}"
    )
    return PostgresBackend(dsn=dsn, namespace=context.target.__class__.__name__)


def build_bigquery_relational(context: RuntimeBackendFactoryContext) -> Any:
    """Build a `BigQueryBackend` from the GCP synth's emitted env vars."""
    from skaal.backends.implementations.data import BigQueryBackend

    binding = require_binding(context)
    env = require_env(context)
    dataset_key, project_key = binding.connection.env_var_keys
    dataset = require_env_var(env, dataset_key, binding.resource_id)
    project = require_env_var(env, project_key, binding.resource_id)
    return BigQueryBackend(project=project, dataset=dataset)


def load_secret_payload(secret_id: str, *, project: str | None) -> dict[str, Any]:
    """Read a Secret Manager secret's latest version as JSON."""
    try:
        client = _secretmanager_client()
    except ImportError as exc:  # pragma: no cover - exercised when extras absent
        raise RuntimeWiringError(
            "Cloud SQL runtime wiring requires google-cloud-secret-manager."
        ) from exc
    name = f"projects/{project or '-'}/secrets/{secret_id}/versions/latest"
    try:
        response = client.access_secret_version(request={"name": name})
    except Exception as exc:
        raise RuntimeWiringError(
            f"Failed to read Secret Manager secret {secret_id!r}: {exc}"
        ) from exc

    raw = response.payload.data.decode("utf-8")
    try:
        payload_obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeWiringError(
            f"Secret Manager payload for {secret_id!r} is not valid JSON: {exc}"
        ) from exc
    if not isinstance(payload_obj, dict):
        raise RuntimeWiringError(f"Secret Manager payload for {secret_id!r} must be a JSON object.")
    return cast(dict[str, Any], payload_obj)


def require_secret_field(payload: dict[str, Any], key: str, resource_id: str) -> str:
    value = payload.get(key)
    if isinstance(value, str) and value:
        return value
    raise RuntimeWiringError(
        f"Secret Manager payload for resource {resource_id!r} is missing field {key!r}."
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
    "build_bigquery_relational",
    "build_firestore_store",
    "build_gcs_blob",
    "build_postgres_relational",
    "build_pubsub_channel",
]
