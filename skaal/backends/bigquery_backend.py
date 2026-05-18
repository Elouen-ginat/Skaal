"""Google BigQuery relational backend (ADR 042).

BigQuery is an analytics warehouse. It does not match the row-updateable
OLTP shape that `PostgresBackend` provides — there are no transactions and
no `SELECT ... FOR UPDATE`. The Skaal contract for a `Table[BigQuery]`
class is therefore narrower:

- `await Sales.native()` returns a `google.cloud.bigquery.Client`. Callers
  drive queries through that client directly; the example in
  `examples/bigquery_sales/` shows the canonical pattern.
- `ensure_relational_schema(model_cls)` creates the dataset and table on
  first connect (idempotent — re-create attempts are swallowed via
  `exists_ok=True`).
- `open_relational_session(model_cls)` is intentionally unsupported and
  raises `NotImplementedError`. Use `await Model.native()` instead.

The BigQuery SDK is synchronous; the public methods wrap the calls in
`asyncio.run_in_executor` so they fit the async storage contract.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

_SQLMODEL_TO_BIGQUERY: dict[str, str] = {
    "INTEGER": "INT64",
    "BIGINT": "INT64",
    "SMALLINT": "INT64",
    "FLOAT": "FLOAT64",
    "REAL": "FLOAT64",
    "DOUBLE": "FLOAT64",
    "NUMERIC": "NUMERIC",
    "BOOLEAN": "BOOL",
    "VARCHAR": "STRING",
    "TEXT": "STRING",
    "STRING": "STRING",
    "DATE": "DATE",
    "DATETIME": "DATETIME",
    "TIMESTAMP": "TIMESTAMP",
    "JSON": "JSON",
    "JSONB": "JSON",
}


def _bigquery_type_for(column: Any) -> str:
    """Return the BigQuery type name for a SQLAlchemy ``Column``."""
    raw = str(column.type).split("(")[0].upper().strip()
    return _SQLMODEL_TO_BIGQUERY.get(raw, "STRING")


class BigQueryBackend:
    """Relational backend for `Table[BigQuery]` pins.

    Args:
        project: GCP project id.
        dataset: BigQuery dataset id. Created on first connect.
        location: BigQuery dataset location. Defaults to ``"US"``.
        table_prefix: Optional prefix prepended to every SQLModel table name.
    """

    def __init__(
        self,
        project: str,
        dataset: str,
        location: str = "US",
        table_prefix: str = "",
    ) -> None:
        self.project = project
        self.dataset = dataset
        self.location = location
        self.table_prefix = table_prefix
        self._client: Any | None = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from google.cloud import bigquery
            except ImportError as exc:  # pragma: no cover - import-time helper
                raise ImportError(
                    "google-cloud-bigquery is required for BigQueryBackend. "
                    "Install it with: pip install google-cloud-bigquery"
                ) from exc
            self._client = bigquery.Client(project=self.project)
        return self._client

    async def _run(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))

    async def native(self) -> Any:
        """Return the underlying ``google.cloud.bigquery.Client``."""
        return self._get_client()

    def _table_name(self, model_cls: type) -> str:
        raw = getattr(model_cls, "__tablename__", None) or model_cls.__name__.lower()
        return f"{self.table_prefix}{raw}"

    def _fully_qualified_table(self, model_cls: type) -> str:
        return f"{self.project}.{self.dataset}.{self._table_name(model_cls)}"

    async def ensure_relational_schema(self, model_cls: type) -> None:
        """Create the dataset and table for *model_cls* if missing.

        Schema columns are derived from the SQLModel table metadata. The
        method is idempotent — a second call is a no-op.
        """

        def _create() -> None:
            from google.cloud import bigquery

            client = self._get_client()
            dataset_id = f"{self.project}.{self.dataset}"
            dataset = bigquery.Dataset(dataset_id)
            dataset.location = self.location
            client.create_dataset(dataset, exists_ok=True)

            table_id = self._fully_qualified_table(model_cls)
            columns = list(model_cls.__table__.columns)  # type: ignore[attr-defined]
            schema = [
                bigquery.SchemaField(
                    column.name,
                    _bigquery_type_for(column),
                    mode="NULLABLE" if column.nullable else "REQUIRED",
                )
                for column in columns
            ]
            table = bigquery.Table(table_id, schema=schema)
            client.create_table(table, exists_ok=True)

        await self._run(_create)

    @asynccontextmanager
    async def open_relational_session(self, model_cls: type) -> AsyncIterator[Any]:
        """Unsupported for BigQuery — use ``await Model.native()`` instead."""
        await self.ensure_relational_schema(model_cls)
        raise NotImplementedError(
            "BigQuery does not support transactional sessions. "
            "Use `await <Model>.native()` to drive queries through the "
            "`google.cloud.bigquery.Client` directly."
        )
        if False:  # pragma: no cover - satisfies AsyncIterator typing
            yield None

    async def close(self) -> None:
        # google-cloud-bigquery clients do not require explicit close.
        self._client = None

    def __repr__(self) -> str:
        return (
            f"BigQueryBackend(project={self.project!r}, dataset={self.dataset!r}, "
            f"location={self.location!r})"
        )


__all__ = ["BigQueryBackend"]
