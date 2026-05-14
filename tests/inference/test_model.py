"""Round-trip and field-validation tests for `skaal.inference.model`."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from skaal.inference.model import (
    Edge,
    EdgeKind,
    InferredPlan,
    InferredResource,
    ResourceKind,
    ResourceOverrides,
    SchemaRef,
    SourceLocation,
)


def _sample_resource(rid: str = "acme.users:Users") -> InferredResource:
    return InferredResource(
        id=rid,
        kind=ResourceKind.STORE,
        source=SourceLocation(module="acme.users", qualname="Users", file="acme/users.py", line=10),
        schema=SchemaRef(model_qualname="User", fingerprint="0" * 16),
    )


def test_resource_kind_enum_has_nine_variants() -> None:
    assert {member.value for member in ResourceKind} == {
        "store",
        "relational",
        "blob",
        "channel",
        "function",
        "asgi_service",
        "schedule",
        "job",
        "secret",
    }


def test_edge_kind_enum_has_five_variants() -> None:
    assert {member.value for member in EdgeKind} == {
        "reads",
        "writes",
        "publishes",
        "subscribes",
        "invokes",
    }


def test_inferred_resource_round_trips() -> None:
    res = _sample_resource()
    payload = res.model_dump_json(by_alias=True)
    assert InferredResource.model_validate_json(payload) == res


def test_inferred_resource_schema_field_uses_alias_in_json() -> None:
    res = _sample_resource()
    payload = res.model_dump(mode="json", by_alias=True)
    assert "schema" in payload
    assert "schema_" not in payload


def test_inferred_resource_frozen() -> None:
    res = _sample_resource()
    with pytest.raises(ValidationError):
        res.id = "other"  # type: ignore[misc]


def test_inferred_resource_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        InferredResource(
            id="x",
            kind=ResourceKind.STORE,
            source=SourceLocation(module="m", qualname="x", file="m.py", line=1),
            unknown="oops",  # type: ignore[call-arg]
        )


def test_inferred_plan_round_trips() -> None:
    plan = InferredPlan(
        app="demo",
        resources=(_sample_resource(),),
        edges=(Edge(source_id="a", target_id="b", kind=EdgeKind.READS),),
        fingerprint="cafebabedeadbeef",
    )
    payload = plan.model_dump_json(by_alias=True)
    assert InferredPlan.model_validate_json(payload) == plan


def test_resource_overrides_defaults_are_none() -> None:
    overrides = ResourceOverrides()
    assert overrides.backend is None
    assert overrides.region is None
    assert overrides.memory_mb is None
    assert overrides.timeout_s is None
    assert overrides.min_concurrency is None
    assert overrides.max_concurrency is None


def test_source_location_from_object_handles_unknown() -> None:
    loc = SourceLocation.from_object(42)
    assert loc.module == "<unknown>"
    assert loc.line == 0
    assert loc.file == "<unknown>"


def test_schema_ref_from_class_returns_none_for_non_model() -> None:
    class NoSchema:
        pass

    assert SchemaRef.from_class(NoSchema) is None
