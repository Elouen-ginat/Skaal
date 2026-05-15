"""Tests for `skaal.deploy.tags_for`."""

from __future__ import annotations

import pytest

from skaal.binding.model import BoundResource, Environment, Target
from skaal.deploy import tags_for
from skaal.inference.model import (
    InferredResource,
    ResourceKind,
    ResourceOverrides,
    SourceLocation,
)


def _make_resource(
    rid: str = "myapp.svc:Cache",
    *,
    backend: str = "redis",
    kind: ResourceKind = ResourceKind.STORE,
    external: bool = False,
) -> BoundResource:
    inferred = InferredResource(
        id=rid,
        kind=kind,
        source=SourceLocation(module="myapp.svc", qualname="Cache", file="?", line=1),
        overrides=ResourceOverrides(),
    )
    return BoundResource(
        inferred=inferred,
        backend=backend,
        pinned=False,
        external=external,
    )


def test_tags_for_returns_canonical_keys() -> None:
    resource = _make_resource()
    env = Environment(name="prod", target=Target.AWS, region="us-east-1")
    tags = tags_for(resource, env, "cafebabe00000001")

    assert tags == {
        "skaal:app": "myapp",
        "skaal:resource_id": "myapp.svc:Cache",
        "skaal:kind": "store",
        "skaal:env": "prod",
        "skaal:target": "aws",
        "skaal:backend": "redis",
        "skaal:fingerprint": "cafebabe00000001",
    }


def test_tags_for_extracts_top_level_package_as_app() -> None:
    """``skaal:app`` is the first dotted segment of the resource module."""
    resource = _make_resource(rid="my_corp.payments.api:Charges")
    env = Environment(name="prod", target=Target.AWS)
    tags = tags_for(resource, env, "deadbeef00000002")
    assert tags["skaal:app"] == "my_corp"


def test_tags_for_handles_top_level_module() -> None:
    resource = _make_resource(rid="counter:Counts", kind=ResourceKind.STORE)
    env = Environment(name="local", target=Target.LOCAL)
    tags = tags_for(resource, env, "0" * 16)
    assert tags["skaal:app"] == "counter"
    assert tags["skaal:target"] == "local"


def test_tags_for_is_per_call_fresh() -> None:
    """Two calls return independent dicts; mutating one does not affect the other."""
    resource = _make_resource()
    env = Environment(name="prod", target=Target.AWS)
    a = dict(tags_for(resource, env, "x" * 16))
    b = dict(tags_for(resource, env, "x" * 16))
    a["skaal:env"] = "modified"
    assert b["skaal:env"] == "prod"


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
def test_tags_for_kind_value_string(kind: ResourceKind, expected: str) -> None:
    resource = _make_resource(kind=kind)
    env = Environment(name="prod", target=Target.AWS)
    tags = tags_for(resource, env, "f" * 16)
    assert tags["skaal:kind"] == expected
