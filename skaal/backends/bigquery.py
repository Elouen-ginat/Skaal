"""Public import path for the `BigQuery` backend token (ADR 042).

Re-exports the token from `skaal.backends._tokens`. User code that pins a
`Table` primitive to BigQuery writes:

    from skaal.backends.bigquery import BigQuery

    class Sales(Table[BigQuery], table=True):
        ...

BigQuery is a non-default backend for the `(relational, gcp)` cell;
`Postgres` (Cloud SQL) remains the default. Use a class-level pin
(`Relational[BigQuery]`) to opt in.
"""

from __future__ import annotations

from skaal.backends._tokens import BigQuery

__all__ = ["BigQuery"]
