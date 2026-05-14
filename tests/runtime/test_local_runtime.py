"""Tests for `LocalRuntime.from_bound_plan` and the adapter dispatch."""

from __future__ import annotations

from pathlib import Path

import pytest

from skaal import App, Store
from skaal.binding import bind
from skaal.binding.model import Environment, LockFile, Target
from skaal.errors import RuntimeAdapterMissing
from skaal.inference.model import (
    InferredPlan,
    InferredResource,
    ResourceKind,
    ResourceOverrides,
    SourceLocation,
)
from skaal.runtime import LocalRuntime


def _plan_for(app: App) -> InferredPlan:
    return app.infer()


def test_runtime_builds_from_empty_plan() -> None:
    app = App("empty")
    plan = _plan_for(app)
    env = Environment(name="local", target=Target.LOCAL)
    bound = bind(plan, env, LockFile())
    runtime = LocalRuntime.from_bound_plan(bound, app)
    assert runtime.routes == []
    assert runtime.mounts == []
    asgi = runtime.build_asgi()
    # Starlette's `Starlette` exposes a `routes` attribute on its router.
    assert hasattr(asgi, "routes")


def test_runtime_registers_function_route(tmp_path: Path) -> None:
    app = App("svc")

    @app.function()
    async def greet(name: str) -> dict[str, str]:
        return {"hello": name}

    env = Environment(name="local", target=Target.LOCAL)
    bound = bind(app.infer(), env, LockFile())
    runtime = LocalRuntime.from_bound_plan(bound, app)
    paths = [r.path for r in runtime.routes]
    assert "/greet" in paths


def test_runtime_wires_store_with_sqlite(tmp_path: Path) -> None:
    app = App("svc")

    @app.storage(kind="kv")
    class Things(Store[dict]):
        pass

    env = Environment(name="local", target=Target.LOCAL)
    bound = bind(app.infer(), env, LockFile())
    runtime = LocalRuntime.from_bound_plan(bound, app)
    # The store adapter staged a startup hook for backend.connect().
    assert runtime.startup_hooks
    assert runtime.shutdown_hooks


def test_runtime_raises_on_unsupported_backend() -> None:
    app = App("svc")

    @app.storage(kind="kv")
    class Cache(Store[dict]):
        pass

    # DynamoDB binds cleanly on an AWS-target env, but the local
    # runtime's store adapter only knows sqlite/redis, so registration
    # surfaces the missing-adapter error.
    plan = InferredPlan(
        app="svc",
        resources=(
            InferredResource(
                id=InferredResource.id_for(Cache),
                kind=ResourceKind.STORE,
                source=SourceLocation.from_object(Cache),
                overrides=ResourceOverrides(backend="dynamodb"),
            ),
        ),
        fingerprint="cafebabe00000002",
    )
    env = Environment(name="prod", target=Target.AWS, region="us-east-1")
    bound = bind(plan, env, LockFile())
    with pytest.raises(RuntimeAdapterMissing):
        LocalRuntime.from_bound_plan(bound, app)


async def test_runtime_function_endpoint_responds(tmp_path: Path) -> None:
    from starlette.requests import Request
    from starlette.testclient import TestClient

    app = App("svc")

    @app.function()
    async def echo(value: str) -> dict[str, str]:
        return {"value": value}

    env = Environment(name="local", target=Target.LOCAL)
    bound = bind(app.infer(), env, LockFile())
    runtime = LocalRuntime.from_bound_plan(bound, app)
    asgi = runtime.build_asgi()

    with TestClient(asgi) as client:
        resp = client.post("/echo", json={"value": "hi"})
        assert resp.status_code == 200
        assert resp.json() == {"result": {"value": "hi"}}

    # Reference Request to make the import "used" — Starlette uses it
    # under the hood, and importing it pulls in the type the endpoint
    # callable receives.
    _ = Request
