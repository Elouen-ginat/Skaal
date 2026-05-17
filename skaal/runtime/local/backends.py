"""Backend factory helpers for the built-in local runtime target."""

from __future__ import annotations

from typing import Any

from skaal.errors import MissingExtraError, RuntimeWiringError
from skaal.runtime._registry import RuntimeBackendFactoryContext


def build_sqlite_store(context: RuntimeBackendFactoryContext) -> Any:
    from skaal.backends.sqlite_backend import SqliteBackend

    bound = require_planned_resource(context)
    path: str = bound.options.get("path", "skaal_local.db")
    return SqliteBackend(path=path, namespace=context.target.__name__)


def build_redis_store(context: RuntimeBackendFactoryContext) -> Any:
    try:
        from skaal.backends.redis_backend import RedisBackend
    except Exception as exc:  # pragma: no cover - import error path
        raise MissingExtraError(
            "redis adapter requires `redis>=5` — install the `redis` extra."
        ) from exc

    bound = require_planned_resource(context)
    url: str = bound.options.get("url", "redis://localhost:6379/0")
    return RedisBackend(url=url, namespace=context.target.__name__)


def build_filesystem_blob(context: RuntimeBackendFactoryContext) -> Any:
    from skaal.backends.file_blob_backend import FileBlobBackend

    bound = require_planned_resource(context)
    root: str = bound.options.get("root", "./skaal_blob")
    return FileBlobBackend(root_path=root, namespace=context.target.__name__)


def build_sqlite_relational(context: RuntimeBackendFactoryContext) -> Any:
    from skaal.backends.sqlite_backend import SqliteBackend

    bound = require_planned_resource(context)
    path: str = bound.options.get("path", "skaal_local.db")
    return SqliteBackend(path=path, namespace=context.target.__name__)


def build_in_process_channel(context: RuntimeBackendFactoryContext) -> Any:
    return None


def require_planned_resource(context: RuntimeBackendFactoryContext) -> Any:
    bound = context.planned_resource
    if bound is None:
        raise RuntimeWiringError(
            f"Runtime target {context.target_name!r} requires a planned resource for "
            f"{context.resource_kind.value}/{context.backend_name}."
        )
    return bound


__all__ = [
    "build_filesystem_blob",
    "build_in_process_channel",
    "build_redis_store",
    "build_sqlite_relational",
    "build_sqlite_store",
]
