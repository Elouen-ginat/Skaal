"""BigQuery sales example — `Table[BigQuery]` end-to-end (ADR 028 §12.6).

Demonstrates a pinned analytics-relational primitive whose backend is
`BigQuery` in every environment. `Sale.native()` resolves to
`google.cloud.bigquery.Client` in Pylance and at runtime.

Run locally against real BigQuery::

    # Configure dataset in `examples/bigquery_sales/skaal.toml`:
    [env.local]
    target = "local"
    [env.local.backends.bigquery]
    project = "acme-dev"
    dataset = "alice_sandbox"

    export GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json
    skaal run examples.bigquery_sales:app

Deploy the schema-managing arm to GCP::

    skaal plan examples.bigquery_sales:app --env prod
    skaal deploy examples.bigquery_sales:app --env prod

`record_sale` inserts via the BigQuery streaming insert API; `top_skus`
runs a SQL aggregate through the native client. Both round-trip against
the real cloud — there is no SQLite substitution because the class is
type-pinned to BigQuery.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlmodel import Field

from skaal import App, Table
from skaal.backends.bigquery import BigQuery

app = App("bigquery-sales")


@app.storage(kind="relational")
class Sale(Table[BigQuery], table=True):
    """One analytics row per completed sale.

    The class body is the row schema; the second generic parameter
    (`BigQuery`) pins the backend at declaration time. `Sale.native()`
    resolves to ``google.cloud.bigquery.Client`` in both Pylance and at
    runtime.
    """

    __tablename__ = "sales"  # type: ignore[assignment]

    id: str = Field(primary_key=True)
    sku: str
    customer: str
    amount_cents: int
    occurred_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@app.expose()
async def record_sale(
    id: str,
    sku: str,
    customer: str,
    amount_cents: int,
    occurred_at: str | None = None,
) -> dict[str, Any]:
    """Insert one sale row via the BigQuery streaming insert API."""
    await Sale.migrate()
    client: Any = await Sale.native()
    occurred = occurred_at or datetime.now(timezone.utc).isoformat()
    row = {
        "id": id,
        "sku": sku,
        "customer": customer,
        "amount_cents": amount_cents,
        "occurred_at": occurred,
    }
    table_ref = f"{client.project}.{Sale.metadata.schema}.{Sale.__tablename__}"  # type: ignore[attr-defined]
    errors = client.insert_rows_json(table_ref, [row])
    if errors:
        return {"error": "insert failed", "details": errors}
    return {"ok": True, "row": row}


@app.expose()
async def top_skus(limit: int = 5) -> dict[str, Any]:
    """Aggregate top SKUs by revenue using a native BigQuery SQL query."""
    await Sale.migrate()
    client: Any = await Sale.native()
    table_ref = f"`{client.project}.{Sale.metadata.schema}.{Sale.__tablename__}`"  # type: ignore[attr-defined]
    query = (
        f"SELECT sku, SUM(amount_cents) AS revenue_cents "
        f"FROM {table_ref} GROUP BY sku ORDER BY revenue_cents DESC LIMIT @limit"
    )
    from google.cloud import bigquery

    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("limit", "INT64", limit)]
    )
    rows = list(client.query(query, job_config=job_config).result())
    return {
        "rows": [{"sku": row["sku"], "revenue_cents": int(row["revenue_cents"])} for row in rows]
    }


__all__ = ["Sale", "app"]
