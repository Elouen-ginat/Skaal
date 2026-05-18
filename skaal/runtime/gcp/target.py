"""Registration for the built-in GCP runtime target (ADR 042)."""

from __future__ import annotations

from skaal.inference.model import ResourceKind
from skaal.runtime._registry import (
    RuntimeBackendFactoryContext,
    RuntimeTargetRegistration,
    register_runtime_target,
)
from skaal.runtime.gcp.backends import (
    build_bigquery_relational,
    build_firestore_store,
    build_gcs_blob,
    build_postgres_relational,
    build_pubsub_channel,
)

GCP_RUNTIME_TARGET_NAME = "gcp"
GCP_RUNTIME_TARGET = RuntimeTargetRegistration(name=GCP_RUNTIME_TARGET_NAME)


def register_builtin_runtime_target() -> RuntimeTargetRegistration:
    register_runtime_target(GCP_RUNTIME_TARGET)

    GCP_RUNTIME_TARGET.register_binding_wirer(ResourceKind.STORE, wire_store_binding)
    GCP_RUNTIME_TARGET.register_binding_wirer(ResourceKind.BLOB, wire_blob_binding)
    GCP_RUNTIME_TARGET.register_binding_wirer(ResourceKind.RELATIONAL, wire_relational_binding)
    GCP_RUNTIME_TARGET.register_binding_wirer(ResourceKind.CHANNEL, wire_channel_binding)

    GCP_RUNTIME_TARGET.register_backend_factory(
        ResourceKind.STORE,
        "firestore",
        build_firestore_store,
    )
    # Reuse the Redis store factory from the AWS package so plain Redis pins
    # work on GCP without duplicating the wiring code.
    from skaal.runtime.aws.backends import build_redis_store

    GCP_RUNTIME_TARGET.register_backend_factory(ResourceKind.STORE, "redis", build_redis_store)
    GCP_RUNTIME_TARGET.register_backend_factory(ResourceKind.BLOB, "gcs", build_gcs_blob)
    GCP_RUNTIME_TARGET.register_backend_factory(
        ResourceKind.RELATIONAL,
        "postgres",
        build_postgres_relational,
    )
    GCP_RUNTIME_TARGET.register_backend_factory(
        ResourceKind.RELATIONAL,
        "bigquery",
        build_bigquery_relational,
    )
    GCP_RUNTIME_TARGET.register_backend_factory(
        ResourceKind.CHANNEL,
        "pubsub",
        build_pubsub_channel,
    )
    # The Redis-channel factory is reused from AWS for cross-cloud parity.
    from skaal.runtime.aws.backends import build_redis_channel

    GCP_RUNTIME_TARGET.register_backend_factory(
        ResourceKind.CHANNEL,
        "redis-channel",
        build_redis_channel,
    )
    return GCP_RUNTIME_TARGET


def wire_store_binding(context: RuntimeBackendFactoryContext) -> None:
    backend = GCP_RUNTIME_TARGET.build_backend(context)
    context.target.wire(backend)


def wire_blob_binding(context: RuntimeBackendFactoryContext) -> None:
    backend = GCP_RUNTIME_TARGET.build_backend(context)
    context.target.wire(backend)


def wire_relational_binding(context: RuntimeBackendFactoryContext) -> None:
    from skaal.table import wire_relational_model

    backend = GCP_RUNTIME_TARGET.build_backend(context)
    wire_relational_model(context.target, backend)


def wire_channel_binding(context: RuntimeBackendFactoryContext) -> None:
    backend = GCP_RUNTIME_TARGET.build_backend(context)
    context.target.wire(backend, backend_name=context.backend_name)


__all__ = [
    "GCP_RUNTIME_TARGET",
    "GCP_RUNTIME_TARGET_NAME",
    "register_builtin_runtime_target",
]
