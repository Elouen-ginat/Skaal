"""Round-trip and validation tests for `StubManifest` (ADR 033 §5.1)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from skaal.stubs.manifest import StubManifest, StubResourceRef


def _make_manifest() -> StubManifest:
    return StubManifest(
        package_name="billing_stubs",
        source_module="services.billing",
        source_app="billing",
        app_fingerprint="abc123def4567890",
        skaal_version="0.4.0a0",
        generated_at=datetime(2026, 5, 16, 12, 0, 0, tzinfo=UTC),
        resources=(
            StubResourceRef(
                id="services.billing:Customers",
                kind="store",
                module="services.billing",
                qualname="Customers",
            ),
            StubResourceRef(
                id="services.billing:signup",
                kind="function",
                module="services.billing",
                qualname="signup",
            ),
        ),
    )


def test_manifest_json_roundtrips_unchanged() -> None:
    manifest = _make_manifest()
    revived = StubManifest.from_json(manifest.to_json())
    assert revived == manifest


def test_manifest_rejects_unknown_keys() -> None:
    with pytest.raises(ValidationError):
        StubManifest.model_validate(
            {
                "package_name": "x",
                "source_module": "x",
                "source_app": "x",
                "skaal_version": "0",
                "generated_at": "2026-05-16T12:00:00Z",
                "resources": [],
                "unexpected": "field",
            }
        )


def test_manifest_resource_ref_rejects_unknown_keys() -> None:
    with pytest.raises(ValidationError):
        StubResourceRef.model_validate(
            {
                "id": "x:y",
                "kind": "store",
                "module": "x",
                "qualname": "y",
                "extra": True,
            }
        )


def test_fingerprint_payload_excludes_timestamp_and_version() -> None:
    """The byte-stable comparison surface omits drift-prone fields.

    A regenerate that does not change any inferred resource should
    produce the same fingerprint payload even if `generated_at` advances
    or `skaal_version` is bumped between runs.
    """
    one = _make_manifest()
    two = one.model_copy(
        update={
            "generated_at": datetime(2026, 6, 1, tzinfo=UTC),
            "skaal_version": "0.4.0a1",
        }
    )
    assert one.fingerprint_payload() == two.fingerprint_payload()


def test_manifest_models_are_frozen() -> None:
    manifest = _make_manifest()
    with pytest.raises(ValidationError):
        manifest.package_name = "other"  # type: ignore[misc]
