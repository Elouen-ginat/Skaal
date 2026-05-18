"""Backend factory helpers for the built-in local runtime target."""

from __future__ import annotations

from typing import Any

from skaal.errors import MissingExtraError, RuntimeWiringError
from skaal.runtime._registry import RuntimeBackendFactoryContext


def build_sqlite_store(context: RuntimeBackendFactoryContext) -> Any:
    from skaal.backends.implementations.data import SqliteBackend

    bound = require_planned_resource(context)
    path: str = bound.options.get("path", "skaal_local.db")
    return SqliteBackend(path=path, namespace=context.target.__name__)


def build_redis_store(context: RuntimeBackendFactoryContext) -> Any:
    try:
        from skaal.backends.implementations.data import RedisBackend
    except Exception as exc:  # pragma: no cover - import error path
        raise MissingExtraError(
            "redis adapter requires `redis>=5` — install the `redis` extra."
        ) from exc

    bound = require_planned_resource(context)
    url: str = bound.options.get("url", "redis://localhost:6379/0")
    return RedisBackend(url=url, namespace=context.target.__name__)


def build_filesystem_blob(context: RuntimeBackendFactoryContext) -> Any:
    from skaal.backends.implementations.blob import FileBlobBackend

    bound = require_planned_resource(context)
    root: str = bound.options.get("root", "./skaal_blob")
    return FileBlobBackend(root_path=root, namespace=context.target.__name__)


def build_sqlite_relational(context: RuntimeBackendFactoryContext) -> Any:
    from skaal.backends.implementations.data import SqliteBackend

    bound = require_planned_resource(context)
    path: str = bound.options.get("path", "skaal_local.db")
    return SqliteBackend(path=path, namespace=context.target.__name__)


def build_in_process_channel(context: RuntimeBackendFactoryContext) -> Any:
    return None


def build_bigquery_relational(context: RuntimeBackendFactoryContext) -> Any:
    """Construct a `BigQueryBackend` for a locally-running app pinned to BigQuery.

    Reads connection details from `[env.local.backends.bigquery]` in
    `skaal.toml` (project + dataset + optional location). The pin flows in
    via `BackendConfig` on the planned resource; falling back to per-env
    overrides keeps `skaal run` against real BigQuery one TOML edit away.
    """
    from skaal.backends.implementations.data import BigQueryBackend

    bound = require_planned_resource(context)
    project = ""
    dataset = ""
    location = "US"
    if bound.backend_config is not None:
        project = bound.backend_config.project or ""
        dataset = bound.backend_config.dataset or ""
        for key, raw in bound.backend_config.options.items():
            if key == "location" and isinstance(raw, str):
                location = raw
    project = bound.options.get("project", project)
    dataset = bound.options.get("dataset", dataset)
    location = bound.options.get("location", location)
    if not project or not dataset:
        raise RuntimeWiringError(
            "BigQuery local runtime requires `project` and `dataset` set under "
            "`[env.local.backends.bigquery]` in `skaal.toml`."
        )
    return BigQueryBackend(project=project, dataset=dataset, location=location)


def require_planned_resource(context: RuntimeBackendFactoryContext) -> Any:
    bound = context.planned_resource
    if bound is None:
        raise RuntimeWiringError(
            f"Runtime target {context.target_name!r} requires a planned resource for "
            f"{context.resource_kind.value}/{context.backend_name}."
        )
    return bound


__all__ = [
    "build_bigquery_relational",
    "build_filesystem_blob",
    "build_in_process_channel",
    "build_redis_store",
    "build_sqlite_relational",
    "build_sqlite_store",
]
