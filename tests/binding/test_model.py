"""Round-trip and field-validation tests for `skaal.binding.model`."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from skaal.binding.model import (
    BackendConfig,
    BoundPlan,
    BoundResource,
    Environment,
    LockEntry,
    LockFile,
    ResourceOverride,
    Target,
)
from skaal.inference.model import InferredResource, ResourceKind, SourceLocation


def _sample_inferred(rid: str = "acme.users:Users") -> InferredResource:
    return InferredResource(
        id=rid,
        kind=ResourceKind.STORE,
        source=SourceLocation(module="acme.users", qualname="Users", file="acme/users.py", line=10),
    )


def test_target_enum_has_three_variants() -> None:
    assert {member.value for member in Target} == {"local", "aws", "gcp"}


def test_environment_round_trips() -> None:
    env = Environment(
        name="prod",
        target=Target.AWS,
        region="eu-west-1",
        overrides={"acme.users:Users": ResourceOverride(backend="dynamodb")},
        backends={"dynamodb": BackendConfig(region="eu-west-1")},
    )
    payload = env.model_dump_json()
    assert Environment.model_validate_json(payload) == env


def test_environment_rejects_extra_keys() -> None:
    with pytest.raises(ValidationError):
        Environment.model_validate({"name": "prod", "target": "aws", "extra": "nope"})


def test_resource_override_round_trips() -> None:
    override = ResourceOverride(backend="redis", region="us-east-1")
    assert ResourceOverride.model_validate_json(override.model_dump_json()) == override


def test_lock_entry_carries_pin_metadata() -> None:
    entry = LockEntry(
        backend="dynamodb",
        pinned_at=datetime(2026, 5, 12, 14, 0, 0, tzinfo=UTC),
        pinned_by="alice@acme.com",
        fingerprint="abc123",
    )
    payload = entry.model_dump_json()
    assert LockEntry.model_validate_json(payload) == entry


def test_lock_file_holds_tuple_keys() -> None:
    entry = LockEntry(
        backend="dynamodb",
        pinned_at=datetime(2026, 5, 12, 14, 0, 0, tzinfo=UTC),
    )
    lock = LockFile(entries={("prod", "acme.users:Users"): entry})
    assert lock.entries[("prod", "acme.users:Users")] == entry


def test_bound_plan_round_trips() -> None:
    inferred = _sample_inferred()
    plan = BoundPlan(
        app="acme",
        environment="local",
        resources=(
            BoundResource(
                inferred=inferred,
                backend="sqlite",
                pinned=False,
            ),
        ),
    )
    payload = plan.model_dump_json(by_alias=True)
    assert BoundPlan.model_validate_json(payload) == plan


def test_bound_plan_is_frozen() -> None:
    plan = BoundPlan(app="acme", environment="local")
    with pytest.raises(ValidationError):
        plan.app = "other"  # type: ignore[misc]


def test_bound_resource_rejects_extra_keys() -> None:
    inferred = _sample_inferred()
    with pytest.raises(ValidationError):
        BoundResource.model_validate(
            {
                "inferred": inferred.model_dump(),
                "backend": "sqlite",
                "pinned": False,
                "unknown": "rejected",
            }
        )
