"""Tests for `skaal.deploy.models` — the typed build-time pydantic shapes."""

from __future__ import annotations

import pytest

from skaal.binding.model import Target
from skaal.deploy.models import (
    BuildContext,
    BuildManifest,
    BuildPyProject,
    ManifestResourceEntry,
)
from skaal.inference.model import ResourceKind


def test_build_context_enum_fields_serialize_to_strings() -> None:
    """`model_dump(mode='json')` yields string enum values for templates."""
    ctx = BuildContext(
        app_name="svc",
        env_name="prod",
        target=Target.AWS,
        user_package="myapp",
        app_target="myapp.app:app",
        python_version="3.11",
        resource_id="myapp.app:greet",
        resource_kind=ResourceKind.FUNCTION,
        resource_bare_name="greet",
        backend="lambda",
        bound_fingerprint="abc123",
        app_fingerprint="def456",
        requirements=("skaal[runtime,aws]",),
    )
    dumped = ctx.model_dump(mode="json")
    assert dumped["target"] == "aws"
    assert dumped["resource_kind"] == "function"
    assert dumped["requirements"] == ["skaal[runtime,aws]"]


def test_build_context_extra_keys_rejected() -> None:
    with pytest.raises(ValueError, match="extra"):
        BuildContext(  # type: ignore[call-arg]
            app_name="svc",
            env_name="prod",
            target=Target.AWS,
            user_package="myapp",
            app_target="myapp.app:app",
            python_version="3.11",
            resource_id="myapp.app:greet",
            resource_kind=ResourceKind.FUNCTION,
            resource_bare_name="greet",
            backend="lambda",
            bound_fingerprint="abc",
            app_fingerprint="def",
            requirements=(),
            stray="nope",
        )


def test_build_manifest_round_trip_via_json() -> None:
    manifest = BuildManifest(
        app="svc",
        environment="prod",
        target=Target.AWS,
        app_fingerprint="a" * 16,
        bound_fingerprint="b" * 16,
        resources=(
            ManifestResourceEntry(
                id="svc.api:greet",
                kind=ResourceKind.FUNCTION,
                backend="lambda",
                slug="greet-12345678",
                external=False,
            ),
        ),
    )
    rendered = manifest.to_json()
    assert rendered.endswith("\n")
    round_tripped = BuildManifest.model_validate_json(rendered)
    assert round_tripped == manifest


def test_manifest_resource_entry_for_resource_builds_from_bound() -> None:
    from skaal.binding.model import BoundResource
    from skaal.inference.model import (
        InferredResource,
        ResourceOverrides,
        SourceLocation,
    )

    inferred = InferredResource(
        id="svc.api:greet",
        kind=ResourceKind.FUNCTION,
        source=SourceLocation(module="svc.api", qualname="greet", file="?", line=1),
        overrides=ResourceOverrides(),
    )
    bound = BoundResource(inferred=inferred, backend="lambda", pinned=False)
    entry = ManifestResourceEntry.for_resource(bound, slug="greet-deadbeef")
    assert entry.id == "svc.api:greet"
    assert entry.kind is ResourceKind.FUNCTION
    assert entry.backend == "lambda"
    assert entry.slug == "greet-deadbeef"
    assert entry.external is False


def test_build_pyproject_alias_field() -> None:
    """`requires_python` round-trips through the `requires-python` alias."""
    project = BuildPyProject(name="x", dependencies=("skaal[runtime,aws]",))
    dumped = project.model_dump(mode="json", by_alias=True)
    assert dumped["requires-python"] == ">=3.11"
    assert dumped["dependencies"] == ["skaal[runtime,aws]"]
