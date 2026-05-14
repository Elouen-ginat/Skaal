"""Tests for the pure `bind(plan, env, lock)` function."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from skaal.binding import bind
from skaal.binding.model import (
    Environment,
    LockEntry,
    LockFile,
    ResourceOverride,
    Target,
)
from skaal.errors import (
    BackendKindMismatch,
    BackendNotAvailableForTarget,
    TypePinViolation,
    UnknownBackendError,
)
from skaal.inference.model import (
    InferredPlan,
    InferredResource,
    ResourceKind,
    ResourceOverrides,
    SourceLocation,
)


def _resource(
    rid: str = "acme.users:Users",
    *,
    kind: ResourceKind = ResourceKind.STORE,
    pinned_backend: str | None = None,
) -> InferredResource:
    overrides = (
        ResourceOverrides(backend=pinned_backend)
        if pinned_backend is not None
        else ResourceOverrides()
    )
    return InferredResource(
        id=rid,
        kind=kind,
        source=SourceLocation(
            module="acme.users", qualname=rid.split(":")[-1], file="acme/users.py", line=10
        ),
        overrides=overrides,
    )


def _plan(*resources: InferredResource) -> InferredPlan:
    return InferredPlan(app="acme", resources=resources, edges=(), fingerprint="x")


def _env(name: str, target: Target, **kwargs: object) -> Environment:
    return Environment(name=name, target=target, **kwargs)  # type: ignore[arg-type]


def test_defaults_branch_local_store() -> None:
    plan = _plan(_resource())
    bound = bind(plan, _env("local", Target.LOCAL), LockFile())
    assert bound.resources[0].backend == "sqlite"
    assert bound.resources[0].pinned is False


def test_defaults_branch_aws_store() -> None:
    plan = _plan(_resource())
    bound = bind(plan, _env("prod", Target.AWS), LockFile())
    assert bound.resources[0].backend == "dynamodb"


def test_defaults_branch_gcp_blob() -> None:
    plan = _plan(_resource("acme.users:Avatars", kind=ResourceKind.BLOB))
    bound = bind(plan, _env("prod", Target.GCP), LockFile())
    assert bound.resources[0].backend == "gcs"


def test_lock_branch_overrides_defaults() -> None:
    res = _resource()
    plan = _plan(res)
    lock = LockFile(
        entries={
            ("local", res.id): LockEntry(
                backend="redis",
                pinned_at=datetime(2026, 5, 12, tzinfo=UTC),
            )
        }
    )
    bound = bind(plan, _env("local", Target.LOCAL), lock)
    assert bound.resources[0].backend == "redis"
    assert bound.resources[0].pinned is True


def test_env_override_branch_overrides_defaults() -> None:
    res = _resource()
    plan = _plan(res)
    env = _env(
        "local",
        Target.LOCAL,
        overrides={res.id: ResourceOverride(backend="redis")},
    )
    bound = bind(plan, env, LockFile())
    assert bound.resources[0].backend == "redis"
    assert bound.resources[0].pinned is False


def test_type_pin_takes_precedence_over_defaults() -> None:
    res = _resource(pinned_backend="redis")
    bound = bind(_plan(res), _env("local", Target.LOCAL), LockFile())
    assert bound.resources[0].backend == "redis"
    assert bound.resources[0].pinned is True


def test_type_pin_violation_when_lock_disagrees() -> None:
    res = _resource(pinned_backend="redis")
    lock = LockFile(
        entries={
            ("local", res.id): LockEntry(
                backend="sqlite",
                pinned_at=datetime(2026, 5, 12, tzinfo=UTC),
            )
        }
    )
    with pytest.raises(TypePinViolation):
        bind(_plan(res), _env("local", Target.LOCAL), lock)


def test_type_pin_violation_when_env_override_disagrees() -> None:
    res = _resource(pinned_backend="redis")
    env = _env(
        "local",
        Target.LOCAL,
        overrides={res.id: ResourceOverride(backend="sqlite")},
    )
    with pytest.raises(TypePinViolation):
        bind(_plan(res), env, LockFile())


def test_backend_not_available_for_target() -> None:
    res = _resource(pinned_backend="dynamodb")
    with pytest.raises(BackendNotAvailableForTarget):
        bind(_plan(res), _env("local", Target.LOCAL), LockFile())


def test_backend_kind_mismatch_for_pinned_class() -> None:
    res = _resource(pinned_backend="s3")
    with pytest.raises(BackendKindMismatch):
        bind(_plan(res), _env("prod", Target.AWS), LockFile())


def test_unknown_backend_in_env_override_raises() -> None:
    res = _resource()
    env = _env(
        "local",
        Target.LOCAL,
        overrides={res.id: ResourceOverride(backend="not-a-real-backend")},
    )
    with pytest.raises(UnknownBackendError):
        bind(_plan(res), env, LockFile())


def test_bind_carries_edges_through_unchanged() -> None:
    plan = _plan(_resource())
    bound = bind(plan, _env("local", Target.LOCAL), LockFile())
    assert bound.edges == plan.edges


def test_bind_propagates_env_region_to_unpinned_resources() -> None:
    plan = _plan(_resource())
    bound = bind(plan, _env("prod", Target.AWS, region="eu-west-1"), LockFile())
    assert bound.resources[0].region == "eu-west-1"


def test_bind_attaches_backend_config_when_env_supplies_it() -> None:
    from skaal.binding.model import BackendConfig

    res = _resource()
    env = _env(
        "local",
        Target.LOCAL,
        backends={"sqlite": BackendConfig(options={"path": "./data.db"})},
    )
    bound = bind(_plan(res), env, LockFile())
    assert bound.resources[0].backend_config is not None
    assert bound.resources[0].backend_config.options == {"path": "./data.db"}
