"""Registration for the built-in AWS runtime target."""

from __future__ import annotations

from skaal.inference.model import ResourceKind
from skaal.runtime._registry import (
    RuntimeBackendFactoryContext,
    RuntimeTargetRegistration,
    register_runtime_target,
)
from skaal.runtime.aws.backends import (
    build_dynamodb_store,
    build_postgres_relational,
    build_redis_channel,
    build_redis_store,
    build_s3_blob,
    build_sqs_channel,
)

AWS_RUNTIME_TARGET_NAME = "aws"
AWS_RUNTIME_TARGET = RuntimeTargetRegistration(name=AWS_RUNTIME_TARGET_NAME)


def register_builtin_runtime_target() -> RuntimeTargetRegistration:
    register_runtime_target(AWS_RUNTIME_TARGET)

    AWS_RUNTIME_TARGET.register_binding_wirer(ResourceKind.STORE, wire_store_binding)
    AWS_RUNTIME_TARGET.register_binding_wirer(ResourceKind.BLOB, wire_blob_binding)
    AWS_RUNTIME_TARGET.register_binding_wirer(ResourceKind.RELATIONAL, wire_relational_binding)
    AWS_RUNTIME_TARGET.register_binding_wirer(ResourceKind.CHANNEL, wire_channel_binding)

    AWS_RUNTIME_TARGET.register_backend_factory(
        ResourceKind.STORE, "dynamodb", build_dynamodb_store
    )
    AWS_RUNTIME_TARGET.register_backend_factory(ResourceKind.STORE, "redis", build_redis_store)
    AWS_RUNTIME_TARGET.register_backend_factory(ResourceKind.BLOB, "s3", build_s3_blob)
    AWS_RUNTIME_TARGET.register_backend_factory(
        ResourceKind.RELATIONAL,
        "postgres",
        build_postgres_relational,
    )
    AWS_RUNTIME_TARGET.register_backend_factory(
        ResourceKind.CHANNEL,
        "redis-channel",
        build_redis_channel,
    )
    AWS_RUNTIME_TARGET.register_backend_factory(ResourceKind.CHANNEL, "sqs", build_sqs_channel)
    return AWS_RUNTIME_TARGET


def wire_store_binding(context: RuntimeBackendFactoryContext) -> None:
    backend = AWS_RUNTIME_TARGET.build_backend(context)
    context.target.wire(backend)


def wire_blob_binding(context: RuntimeBackendFactoryContext) -> None:
    backend = AWS_RUNTIME_TARGET.build_backend(context)
    context.target.wire(backend)


def wire_relational_binding(context: RuntimeBackendFactoryContext) -> None:
    from skaal.table import wire_relational_model

    backend = AWS_RUNTIME_TARGET.build_backend(context)
    wire_relational_model(context.target, backend)


def wire_channel_binding(context: RuntimeBackendFactoryContext) -> None:
    backend = AWS_RUNTIME_TARGET.build_backend(context)
    context.target.wire(backend, backend_name=context.backend_name)


__all__ = [
    "AWS_RUNTIME_TARGET",
    "AWS_RUNTIME_TARGET_NAME",
    "register_builtin_runtime_target",
]
