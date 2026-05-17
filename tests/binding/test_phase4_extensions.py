"""Tests for the Phase 4 `Plan` extensions (ADR 032 §4.3)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from skaal.binding import plan
from skaal.binding.model import Environment, LockEntry, LockFile, Target
from skaal.errors import TypePinViolation
from skaal.inference.model import (
    Blueprint,
    BlueprintResource,
    Overrides,
    ResourceKind,
    SourceLocation,
)


def _store_resource(rid: str = "acme.users:Users") -> BlueprintResource:
    return BlueprintResource(
        id=rid,
        kind=ResourceKind.STORE,
        source=SourceLocation(
            module="acme.users", qualname=rid.split(":")[-1], file="acme/users.py", line=1
        ),
    )


def _external_resource(rid: str = "acme.legacy:LegacyDb") -> BlueprintResource:
    return BlueprintResource(
        id=rid,
        kind=ResourceKind.RELATIONAL,
        source=SourceLocation(
            module="acme.legacy", qualname=rid.split(":")[-1], file="acme/legacy.py", line=1
        ),
        overrides=Overrides(
            backend="postgres",
            external=True,
            external_name="legacy_db",
        ),
    )


def _blueprint(*resources: BlueprintResource, fingerprint: str = "deadbeef00001234") -> Blueprint:
    return Blueprint(app="acme", resources=resources, edges=(), fingerprint=fingerprint)


def test_bind_carries_app_fingerprint() -> None:
    current_blueprint = _blueprint(_store_resource(), fingerprint="cafebabe00001111")
    env = Environment(name="local", target=Target.LOCAL)
    bound = plan(current_blueprint, env, LockFile())
    assert bound.app_fingerprint == "cafebabe00001111"


def test_bind_computes_bound_fingerprint() -> None:
    current_blueprint = _blueprint(_store_resource())
    env = Environment(name="local", target=Target.LOCAL)
    bound = plan(current_blueprint, env, LockFile())
    assert len(bound.bound_fingerprint) == 16
    assert all(c in "0123456789abcdef" for c in bound.bound_fingerprint)


def test_bound_fingerprint_deterministic() -> None:
    plan_a = _blueprint(_store_resource("acme:A"), _store_resource("acme:B"))
    plan_b = _blueprint(_store_resource("acme:B"), _store_resource("acme:A"))
    env = Environment(name="local", target=Target.LOCAL)
    a = plan(plan_a, env, LockFile())
    b = plan(plan_b, env, LockFile())
    assert a.bound_fingerprint == b.bound_fingerprint


def test_bound_fingerprint_ignores_lock_pinned_flag() -> None:
    current_blueprint = _blueprint(_store_resource())
    env = Environment(name="local", target=Target.LOCAL)
    unlocked = plan(current_blueprint, env, LockFile())
    locked = plan(
        current_blueprint,
        env,
        LockFile(
            entries={
                ("local", "acme.users:Users"): LockEntry(
                    backend=unlocked.resources[0].backend,
                    region=unlocked.resources[0].region,
                    pinned_at=datetime.now(UTC),
                    pinned_by="test",
                    fingerprint=unlocked.bound_fingerprint,
                )
            }
        ),
    )
    assert unlocked.bound_fingerprint == locked.bound_fingerprint


def test_external_flag_propagates_to_bound_resource() -> None:
    current_blueprint = _blueprint(_external_resource())
    env = Environment(name="local", target=Target.LOCAL)
    bound = plan(current_blueprint, env, LockFile())
    assert len(bound.resources) == 1
    bound_resource = bound.resources[0]
    assert bound_resource.external is True
    assert bound_resource.external_name == "legacy_db"
    assert bound_resource.backend == "postgres"
    assert bound_resource.pinned is True


def test_external_resource_without_pin_raises() -> None:
    resource = BlueprintResource(
        id="acme:NoPinExternal",
        kind=ResourceKind.STORE,
        source=SourceLocation(module="acme", qualname="NoPinExternal", file="acme/x.py", line=1),
        overrides=Overrides(external=True, external_name="x"),
    )
    current_blueprint = _blueprint(resource)
    env = Environment(name="local", target=Target.LOCAL)
    with pytest.raises(TypePinViolation):
        plan(current_blueprint, env, LockFile())


def test_un_pinned_resource_has_external_false() -> None:
    current_blueprint = _blueprint(_store_resource())
    env = Environment(name="local", target=Target.LOCAL)
    bound = plan(current_blueprint, env, LockFile())
    assert bound.resources[0].external is False
    assert bound.resources[0].external_name is None
