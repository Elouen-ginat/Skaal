"""Determinism tests for `skaal.inference.fingerprint`."""

from __future__ import annotations

from skaal.inference.fingerprint import fingerprint_plan, fingerprint_resource
from skaal.inference.model import (
    Edge,
    EdgeKind,
    InferredPlan,
    InferredResource,
    ResourceKind,
    SourceLocation,
)


def _resource(rid: str, kind: ResourceKind = ResourceKind.STORE) -> InferredResource:
    return InferredResource(
        id=rid,
        kind=kind,
        source=SourceLocation(module="m", qualname=rid, file="m.py", line=1),
    )


def test_fingerprint_is_sixteen_hex_chars() -> None:
    plan = InferredPlan(app="demo", resources=(_resource("a"),))
    fp = fingerprint_plan(plan)
    assert len(fp) == 16
    assert all(c in "0123456789abcdef" for c in fp)


def test_fingerprint_is_stable_across_resource_ordering() -> None:
    plan_a = InferredPlan(app="demo", resources=(_resource("a"), _resource("b")))
    plan_b = InferredPlan(app="demo", resources=(_resource("b"), _resource("a")))
    assert fingerprint_plan(plan_a) == fingerprint_plan(plan_b)


def test_fingerprint_changes_when_a_resource_is_added() -> None:
    plan_a = InferredPlan(app="demo", resources=(_resource("a"),))
    plan_b = InferredPlan(app="demo", resources=(_resource("a"), _resource("b")))
    assert fingerprint_plan(plan_a) != fingerprint_plan(plan_b)


def test_fingerprint_changes_when_a_resource_kind_changes() -> None:
    plan_a = InferredPlan(app="demo", resources=(_resource("a", ResourceKind.STORE),))
    plan_b = InferredPlan(app="demo", resources=(_resource("a", ResourceKind.BLOB),))
    assert fingerprint_plan(plan_a) != fingerprint_plan(plan_b)


def test_fingerprint_excludes_its_own_field() -> None:
    """Recomputing the fingerprint on a plan that already has one is idempotent."""
    plan = InferredPlan(app="demo", resources=(_resource("a"),))
    fp = fingerprint_plan(plan)
    fingerprinted = plan.with_fingerprint(fp)
    assert fingerprint_plan(fingerprinted) == fp


def test_fingerprint_is_stable_across_edge_ordering() -> None:
    edges_a = (
        Edge(source_id="a", target_id="b", kind=EdgeKind.READS),
        Edge(source_id="c", target_id="d", kind=EdgeKind.WRITES),
    )
    edges_b = (
        Edge(source_id="c", target_id="d", kind=EdgeKind.WRITES),
        Edge(source_id="a", target_id="b", kind=EdgeKind.READS),
    )
    plan_a = InferredPlan(app="demo", resources=(_resource("a"),), edges=edges_a)
    plan_b = InferredPlan(app="demo", resources=(_resource("a"),), edges=edges_b)
    assert fingerprint_plan(plan_a) == fingerprint_plan(plan_b)


def test_fingerprint_resource_returns_sixteen_hex_chars() -> None:
    fp = fingerprint_resource(_resource("a"))
    assert len(fp) == 16
    assert all(c in "0123456789abcdef" for c in fp)


def test_fingerprint_resource_differs_by_id() -> None:
    assert fingerprint_resource(_resource("a")) != fingerprint_resource(_resource("b"))
