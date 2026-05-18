"""Registration for the built-in local runtime target."""

from __future__ import annotations

from skaal.inference.model import ResourceKind
from skaal.runtime._registry import RuntimeTargetRegistration, register_runtime_target
from skaal.runtime.local.adapters import (
    asgi as asgi_adapter,
)
from skaal.runtime.local.adapters import (
    blob as blob_adapter,
)
from skaal.runtime.local.adapters import (
    channel as channel_adapter,
)
from skaal.runtime.local.adapters import (
    function as function_adapter,
)
from skaal.runtime.local.adapters import (
    job as job_adapter,
)
from skaal.runtime.local.adapters import (
    relational as relational_adapter,
)
from skaal.runtime.local.adapters import (
    schedule as schedule_adapter,
)
from skaal.runtime.local.adapters import (
    secret as secret_adapter,
)
from skaal.runtime.local.adapters import (
    store as store_adapter,
)
from skaal.runtime.local.backends import (
    build_bigquery_relational,
    build_filesystem_blob,
    build_in_process_channel,
    build_redis_store,
    build_sqlite_relational,
    build_sqlite_store,
)

LOCAL_RUNTIME_TARGET_NAME = "local"
LOCAL_RUNTIME_TARGET = RuntimeTargetRegistration(name=LOCAL_RUNTIME_TARGET_NAME)


def register_builtin_runtime_target() -> RuntimeTargetRegistration:
    register_runtime_target(LOCAL_RUNTIME_TARGET)

    LOCAL_RUNTIME_TARGET.register_adapter(ResourceKind.STORE, store_adapter.register)
    LOCAL_RUNTIME_TARGET.register_adapter(ResourceKind.RELATIONAL, relational_adapter.register)
    LOCAL_RUNTIME_TARGET.register_adapter(ResourceKind.BLOB, blob_adapter.register)
    LOCAL_RUNTIME_TARGET.register_adapter(ResourceKind.CHANNEL, channel_adapter.register)
    LOCAL_RUNTIME_TARGET.register_adapter(ResourceKind.FUNCTION, function_adapter.register)
    LOCAL_RUNTIME_TARGET.register_adapter(ResourceKind.SCHEDULE, schedule_adapter.register)
    LOCAL_RUNTIME_TARGET.register_adapter(ResourceKind.JOB, job_adapter.register)
    LOCAL_RUNTIME_TARGET.register_adapter(ResourceKind.ASGI_SERVICE, asgi_adapter.register)
    LOCAL_RUNTIME_TARGET.register_adapter(ResourceKind.SECRET, secret_adapter.register)

    LOCAL_RUNTIME_TARGET.register_backend_factory(ResourceKind.STORE, "sqlite", build_sqlite_store)
    LOCAL_RUNTIME_TARGET.register_backend_factory(ResourceKind.STORE, "redis", build_redis_store)
    LOCAL_RUNTIME_TARGET.register_backend_factory(
        ResourceKind.BLOB,
        "filesystem-blob",
        build_filesystem_blob,
    )
    LOCAL_RUNTIME_TARGET.register_backend_factory(
        ResourceKind.RELATIONAL,
        "sqlite",
        build_sqlite_relational,
    )
    LOCAL_RUNTIME_TARGET.register_backend_factory(
        ResourceKind.RELATIONAL,
        "bigquery",
        build_bigquery_relational,
    )
    LOCAL_RUNTIME_TARGET.register_backend_factory(
        ResourceKind.CHANNEL,
        "in-process",
        build_in_process_channel,
    )
    return LOCAL_RUNTIME_TARGET


__all__ = [
    "LOCAL_RUNTIME_TARGET",
    "LOCAL_RUNTIME_TARGET_NAME",
    "register_builtin_runtime_target",
]
