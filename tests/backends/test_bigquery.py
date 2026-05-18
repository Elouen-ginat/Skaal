"""Tests for the `BigQuery` typed `Backend` token (ADR 042)."""

from __future__ import annotations

import pytest

from skaal.backends.tokens import BigQuery
from skaal.binding.model import Target
from skaal.binding.registry import lookup, lookup_token


def test_bigquery_token_is_registered() -> None:
    entry = lookup("bigquery")
    assert entry.token_class is BigQuery


def test_bigquery_token_round_trips_through_lookup_token() -> None:
    entry = lookup_token(BigQuery)
    assert entry.name == "bigquery"


def test_bigquery_targets_local_and_gcp() -> None:
    """§12.6 requires BigQuery to bind locally too."""
    entry = lookup_token(BigQuery)
    assert Target.LOCAL in entry.targets
    assert Target.GCP in entry.targets


def test_bigquery_supports_only_relational_kind() -> None:
    entry = lookup_token(BigQuery)
    assert {kind.value for kind in entry.kinds} == {"relational"}


def test_bigquery_is_not_a_default_for_relational_on_gcp() -> None:
    """Postgres remains the GCP default; BigQuery is opt-in via type pin."""
    from skaal.binding.registry import default_entry_for
    from skaal.inference.model import ResourceKind

    default = default_entry_for(ResourceKind.RELATIONAL, Target.GCP)
    assert default.name == "postgres"


def test_bigquery_pin_flows_through_table_class() -> None:
    """`Table[BigQuery]` flows into `ResourceOverrides.backend`."""
    from sqlmodel import Field

    from skaal import App
    from skaal.table import Table

    app = App("bigquery-pin-test")

    @app.storage(kind="relational")
    class Sales(Table[BigQuery], table=True):
        __tablename__ = "sales_for_test"  # type: ignore[assignment]

        id: str = Field(primary_key=True)
        sku: str

    inferred = getattr(Sales, "__skaal_inferred__", None)
    assert inferred is not None
    assert inferred.overrides.backend == "bigquery"


def test_bigquery_backend_factory_lazy_loads() -> None:
    pytest.importorskip("google.cloud.bigquery")
    from skaal.backends import BigQueryBackend

    backend = BigQueryBackend(project="example-proj", dataset="ds")
    assert backend.project == "example-proj"
    assert backend.dataset == "ds"
    assert backend.location == "US"
