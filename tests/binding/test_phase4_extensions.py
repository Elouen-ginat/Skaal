"""Tests for the Phase 4 `BoundPlan` extensions (ADR 032 §4.3)."""

from __future__ import annotations

import pytest

from skaal.binding import bind
from skaal.binding.model import Environment, LockFile, Target
from skaal.errors import TypePinViolation
from skaal.inference.model import (
    InferredPlan,
    InferredResource,
    ResourceKind,
    ResourceOverrides,
    SourceLocation,
)


def _store_resource(rid: str = "acme.users:Users") -> InferredResource:
    return InferredResource(
        id=rid,
        kind=ResourceKind.STORE,
        source=SourceLocation(
            module="acme.users", qualname=rid.split(":")[-1], file="acme/users.py", line=1
        ),
    )


def _external_resource(rid: str = "acme.legacy:LegacyDb") -> InferredResource:
    return InferredResource(
        id=rid,
        kind=ResourceKind.RELATIONAL,
        source=SourceLocation(
            module="acme.legacy", qualname=rid.split(":")[-1], file="acme/legacy.py", line=1
        ),
        overrides=ResourceOverrides(
            backend="postgres",
            external=True,
            external_name="legacy_db",
        ),
    )


def _plan(*resources: InferredResource, fingerprint: str = "deadbeef00001234") -> InferredPlan:
    return InferredPlan(app="acme", resources=resources, edges=(), fingerprint=fingerprint)


def test_bind_carries_app_fingerprint() -> None:
    plan = _plan(_store_resource(), fingerprint="cafebabe00001111")
    env = Environment(name="local", target=Target.LOCAL)
    bound = bind(plan, env, LockFile())
    assert bound.app_fingerprint == "cafebabe00001111"


def test_bind_computes_bound_fingerprint() -> None:
    plan = _plan(_store_resource())
    env = Environment(name="local", target=Target.LOCAL)
    bound = bind(plan, env, LockFile())
    assert len(bound.bound_fingerprint) == 16
    assert all(c in "0123456789abcdef" for c in bound.bound_fingerprint)


def test_bound_fingerprint_deterministic() -> None:
    plan_a = _plan(_store_resource("acme:A"), _store_resource("acme:B"))
    plan_b = _plan(_store_resource("acme:B"), _store_resource("acme:A"))
    env = Environment(name="local", target=Target.LOCAL)
    a = bind(plan_a, env, LockFile())
    b = bind(plan_b, env, LockFile())
    assert a.bound_fingerprint == b.bound_fingerprint


def test_external_flag_propagates_to_bound_resource() -> None:
    plan = _plan(_external_resource())
    env = Environment(name="local", target=Target.LOCAL)
    bound = bind(plan, env, LockFile())
    assert len(bound.resources) == 1
    bound_resource = bound.resources[0]
    assert bound_resource.external is True
    assert bound_resource.external_name == "legacy_db"
    assert bound_resource.backend == "postgres"
    assert bound_resource.pinned is True


def test_external_resource_without_pin_raises() -> None:
    resource = InferredResource(
        id="acme:NoPinExternal",
        kind=ResourceKind.STORE,
        source=SourceLocation(module="acme", qualname="NoPinExternal", file="acme/x.py", line=1),
        overrides=ResourceOverrides(external=True, external_name="x"),
    )
    plan = _plan(resource)
    env = Environment(name="local", target=Target.LOCAL)
    with pytest.raises(TypePinViolation):
        bind(plan, env, LockFile())


def test_un_pinned_resource_has_external_false() -> None:
    plan = _plan(_store_resource())
    env = Environment(name="local", target=Target.LOCAL)
    bound = bind(plan, env, LockFile())
    assert bound.resources[0].external is False
    assert bound.resources[0].external_name is None
