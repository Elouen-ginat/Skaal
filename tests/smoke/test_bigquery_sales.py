"""ADR 028 §12 criterion 6 — `Relational[BigQuery]` resolves a real client.

Implements ADR 035 Decision 3: a maintainer-run smoke gated on
`SKAAL_RUN_BIGQUERY_SMOKE=1` and `GOOGLE_APPLICATION_CREDENTIALS`. The flow
runs the `recent_sales` function from `examples/bigquery_sales/` against a
real BigQuery dataset and asserts the returned client is the typed
`google.cloud.bigquery.Client` (the criterion's `.native()` guarantee).

The example itself is the §7.1 leftover blocked on the grouped
`skaal.backends.tokens` package being available; until that ships the import
fails and the test skips with a clear reason. Once the token lands the test
starts exercising the live path automatically.
"""

from __future__ import annotations

import importlib

import pytest

from tests.smoke.conftest import requires_bigquery_gate


def test_bigquery_native_returns_real_client() -> None:
    """`await Sales.native()` resolves to `google.cloud.bigquery.Client`."""
    requires_bigquery_gate()

    try:
        importlib.import_module("skaal.backends.tokens")
    except ModuleNotFoundError as exc:
        pytest.skip(
            "`skaal.backends.tokens` not yet registered — the BigQuery "
            f"backend token is a Phase 7 §7.1 leftover ({exc})."
        )

    try:
        example = importlib.import_module("examples.bigquery_sales.app")
    except ModuleNotFoundError as exc:
        pytest.skip(
            "`examples/bigquery_sales/` not present — the example is the "
            f"§7.1 leftover that pairs with the BigQuery token ({exc})."
        )

    bigquery = pytest.importorskip(
        "google.cloud.bigquery",
        reason="`google-cloud-bigquery` required to assert the native client type.",
    )

    sales = getattr(example, "Sales", None)
    assert sales is not None, "examples.bigquery_sales.app must expose a `Sales` table."

    import asyncio

    client = asyncio.run(sales.native())
    assert isinstance(client, bigquery.Client), (
        f"Sales.native() returned {type(client).__name__}, "
        "expected google.cloud.bigquery.Client (ADR 028 §12 criterion 6)."
    )

    recent_sales = getattr(example, "recent_sales", None)
    if recent_sales is not None:
        rows = asyncio.run(recent_sales())
        assert isinstance(rows, list), f"recent_sales() must return a list, got {type(rows)!r}."
