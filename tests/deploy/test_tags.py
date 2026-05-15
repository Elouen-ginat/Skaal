"""Tests for `skaal.deploy.tags_for` and the `SkaalTags` pydantic shape."""

from __future__ import annotations

import pytest

from skaal.binding.model import BoundResource, Environment, Target
from skaal.deploy import SkaalTags, tags_for
from skaal.inference.model import (
    InferredResource,
    ResourceKind,
    ResourceOverrides,
    SourceLocation,
)


def _make_resource(
    *,
    module: str = "myapp.svc",
    qualname: str = "Cache",
    backend: str = "redis",
    kind: ResourceKind = ResourceKind.STORE,
    external: bool = False,
) -> BoundResource:
    """Build a `BoundResource` whose ``id`` and ``source`` agree."""
    inferred = InferredResource(
        id=f"{module}:{qualname}",
        kind=kind,
        source=SourceLocation(module=module, qualname=qualname, file="?", line=1),
        overrides=ResourceOverrides(),
    )
    return BoundResource(
        inferred=inferred,
        backend=backend,
        pinned=False,
        external=external,
    )


def test_tags_for_returns_typed_skaal_tags() -> None:
    """`tags_for` returns a `SkaalTags` pydantic model, not a bare dict."""
    resource = _make_resource()
    env = Environment(name="prod", target=Target.AWS, region="us-east-1")
    tags = tags_for(resource, env, "cafebabe00000001")

    assert isinstance(tags, SkaalTags)
    assert tags.app == "myapp"
    assert tags.resource_id == "myapp.svc:Cache"
    assert tags.kind is ResourceKind.STORE
    assert tags.env == "prod"
    assert tags.target is Target.AWS
    assert tags.backend == "redis"
    assert tags.fingerprint == "cafebabe00000001"


def test_skaal_tags_as_mapping_emits_prefixed_keys() -> None:
    """`as_mapping()` produces the Pulumi wire form with `skaal:` prefixes."""
    resource = _make_resource()
    env = Environment(name="prod", target=Target.AWS)
    tags = tags_for(resource, env, "cafebabe00000001").as_mapping()

    assert tags == {
        "skaal:app": "myapp",
        "skaal:resource_id": "myapp.svc:Cache",
        "skaal:kind": "store",
        "skaal:env": "prod",
        "skaal:target": "aws",
        "skaal:backend": "redis",
        "skaal:fingerprint": "cafebabe00000001",
    }


def test_skaal_tags_for_resource_extracts_top_level_package() -> None:
    """`SkaalTags.for_resource` reads `top_package` from the structured source."""
    resource = _make_resource(module="my_corp.payments.api", qualname="Charges")
    env = Environment(name="prod", target=Target.AWS)
    tags = SkaalTags.for_resource(resource, env, "deadbeef00000002")
    assert tags.app == "my_corp"


def test_skaal_tags_handles_top_level_module() -> None:
    resource = _make_resource(module="counter", qualname="Counts")
    env = Environment(name="local", target=Target.LOCAL)
    tags = tags_for(resource, env, "0" * 16)
    assert tags.app == "counter"
    assert tags.target is Target.LOCAL


def test_skaal_tags_is_frozen() -> None:
    resource = _make_resource()
    env = Environment(name="prod", target=Target.AWS)
    tags = tags_for(resource, env, "f" * 16)
    with pytest.raises(Exception):
        tags.env = "dev"  # type: ignore[misc]


def test_skaal_tags_extra_keys_rejected() -> None:
    """`extra="forbid"` is what makes the tag schema stable across releases."""
    with pytest.raises(ValueError, match="extra"):
        SkaalTags(  # type: ignore[call-arg]
            app="x",
            resource_id="x:y",
            kind=ResourceKind.STORE,
            env="prod",
            target=Target.AWS,
            backend="redis",
            fingerprint="f" * 16,
            unexpected="not allowed",
        )


@pytest.mark.parametrize(
    "kind,expected",
    [
        (ResourceKind.FUNCTION, "function"),
        (ResourceKind.JOB, "job"),
        (ResourceKind.SCHEDULE, "schedule"),
        (ResourceKind.ASGI_SERVICE, "asgi_service"),
        (ResourceKind.SECRET, "secret"),
    ],
)
def test_skaal_tags_kind_value_string(kind: ResourceKind, expected: str) -> None:
    resource = _make_resource(kind=kind)
    env = Environment(name="prod", target=Target.AWS)
    mapping = tags_for(resource, env, "f" * 16).as_mapping()
    assert mapping["skaal:kind"] == expected
