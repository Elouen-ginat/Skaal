"""Tests for the built-in GCP runtime target (ADR 042)."""

from __future__ import annotations

from skaal.inference.model import ResourceKind
from skaal.runtime._registry import get_runtime_target
from skaal.runtime.gcp.target import GCP_RUNTIME_TARGET_NAME


def test_gcp_runtime_target_is_registered() -> None:
    target = get_runtime_target(GCP_RUNTIME_TARGET_NAME)
    assert target.name == GCP_RUNTIME_TARGET_NAME


def test_gcp_runtime_has_store_factories() -> None:
    target = get_runtime_target(GCP_RUNTIME_TARGET_NAME)
    assert target.has_backend_factory(ResourceKind.STORE, "firestore")
    assert target.has_backend_factory(ResourceKind.STORE, "redis")


def test_gcp_runtime_has_relational_factories() -> None:
    target = get_runtime_target(GCP_RUNTIME_TARGET_NAME)
    assert target.has_backend_factory(ResourceKind.RELATIONAL, "postgres")
    assert target.has_backend_factory(ResourceKind.RELATIONAL, "bigquery")


def test_gcp_runtime_has_blob_factory() -> None:
    target = get_runtime_target(GCP_RUNTIME_TARGET_NAME)
    assert target.has_backend_factory(ResourceKind.BLOB, "gcs")


def test_gcp_runtime_has_channel_factories() -> None:
    target = get_runtime_target(GCP_RUNTIME_TARGET_NAME)
    assert target.has_backend_factory(ResourceKind.CHANNEL, "pubsub")
    assert target.has_backend_factory(ResourceKind.CHANNEL, "redis-channel")


def test_local_runtime_accepts_bigquery_for_relational() -> None:
    """§12.6: `Table[BigQuery]` must run locally per `env.local.backends.bigquery`."""
    target = get_runtime_target("local")
    assert target.has_backend_factory(ResourceKind.RELATIONAL, "bigquery")
