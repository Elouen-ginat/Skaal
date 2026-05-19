"""Tests for `LocalRuntime.from_bound_plan` and the adapter dispatch."""

from __future__ import annotations

from pathlib import Path

import pytest

from skaal import App, Module, Store
from skaal.binding import plan as build_plan
from skaal.binding.model import Environment, LockFile, Target
from skaal.errors import RuntimeAdapterMissing
from skaal.inference.model import (
    Blueprint,
    BlueprintResource,
    Overrides,
    ResourceKind,
    SourceLocation,
)
from skaal.runtime import LocalRuntime


def _plan_for(app: App) -> Blueprint:
    return app.blueprint()


def test_runtime_builds_from_empty_plan() -> None:
    app = App("empty")
    env = Environment(name="local", target=Target.LOCAL)
    bound = app.plan(env, lock=LockFile())
    runtime = LocalRuntime.from_bound_plan(bound, app)
    assert runtime.routes == []
    assert runtime.mounts == []
    asgi = runtime.build_asgi()
    # Starlette's `Starlette` exposes a `routes` attribute on its router.
    assert hasattr(asgi, "routes")


def test_runtime_registers_function_route(tmp_path: Path) -> None:
    app = App("svc")

    @app.expose()
    async def greet(name: str) -> dict[str, str]:
        return {"hello": name}

    env = Environment(name="local", target=Target.LOCAL)
    bound = app.plan(env, lock=LockFile())
    runtime = LocalRuntime.from_bound_plan(bound, app)
    paths = [r.path for r in runtime.routes]
    assert "/greet" in paths


def test_runtime_resolves_exported_submodule_function() -> None:
    app = App("svc")
    analytics = Module("analytics")

    @analytics.expose()
    async def record_event(name: str) -> dict[str, str]:
        return {"name": name}

    analytics.export(record_event)
    app.use(analytics, namespace="analytics")

    env = Environment(name="local", target=Target.LOCAL)
    bound = app.plan(env, lock=LockFile())
    runtime = LocalRuntime.from_bound_plan(bound, app)

    assert "svc.record_event" in runtime.state.invokables
    assert "/record_event" in [route.path for route in runtime.routes]


def test_runtime_wires_store_with_sqlite(tmp_path: Path) -> None:
    app = App("svc")

    @app.storage(kind="kv")
    class Things(Store[dict]):
        pass

    env = Environment(name="local", target=Target.LOCAL)
    bound = app.plan(env, lock=LockFile())
    runtime = LocalRuntime.from_bound_plan(bound, app)
    # The store adapter staged a startup hook for backend.connect().
    assert runtime.startup_hooks
    assert runtime.shutdown_hooks


def test_runtime_registers_local_job_queue_route() -> None:
    app = App("svc")

    @app.job()
    async def reindex(user_id: str) -> None:
        _ = user_id

    env = Environment(name="local", target=Target.LOCAL)
    bound = app.plan(env, lock=LockFile())
    runtime = LocalRuntime.from_bound_plan(bound, app)

    assert "/_jobs/reindex/enqueue" in [route.path for route in runtime.routes]
    assert "reindex" in runtime.state.job_queues


def test_runtime_raises_on_unsupported_backend() -> None:
    app = App("svc")

    @app.storage(kind="kv")
    class Cache(Store[dict]):
        pass

    # DynamoDB binds cleanly on an AWS-target env, but the local
    # runtime's store adapter only knows sqlite/redis, so registration
    # surfaces the missing-adapter error.
    current_blueprint = Blueprint(
        app="svc",
        resources=(
            BlueprintResource(
                id=BlueprintResource.id_for(Cache),
                kind=ResourceKind.STORE,
                source=SourceLocation.from_object(Cache),
                overrides=Overrides(backend="dynamodb"),
            ),
        ),
        fingerprint="cafebabe00000002",
    )
    env = Environment(name="prod", target=Target.AWS, region="us-east-1")
    bound = build_plan(current_blueprint, env, LockFile())
    with pytest.raises(RuntimeAdapterMissing):
        LocalRuntime.from_bound_plan(bound, app)


async def test_runtime_function_endpoint_responds(tmp_path: Path) -> None:
    from starlette.requests import Request
    from starlette.testclient import TestClient

    app = App("svc")

    @app.expose()
    async def echo(value: str) -> dict[str, str]:
        return {"value": value}

    env = Environment(name="local", target=Target.LOCAL)
    bound = app.plan(env, lock=LockFile())
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


async def test_runtime_invoke_dispatches_in_process() -> None:
    app = App("svc")

    @app.expose()
    async def echo(value: str) -> dict[str, str]:
        return {"value": value}

    env = Environment(name="local", target=Target.LOCAL)
    bound = app.plan(env, lock=LockFile())
    runtime = LocalRuntime.from_bound_plan(bound, app)

    result = await runtime.invoke("svc.echo", {"value": "hi"})
    assert result == {"value": "hi"}


async def test_runtime_invoke_unknown_raises_key_error() -> None:
    app = App("svc")
    env = Environment(name="local", target=Target.LOCAL)
    bound = app.plan(env, lock=LockFile())
    runtime = LocalRuntime.from_bound_plan(bound, app)

    with pytest.raises(KeyError, match=r"svc\.nope"):
        await runtime.invoke("svc.nope", {})


async def test_runtime_invoke_stream_yields_items() -> None:
    app = App("svc")

    @app.expose()
    async def stream(prompt: str):
        for token in prompt.split():
            yield token

    env = Environment(name="local", target=Target.LOCAL)
    bound = app.plan(env, lock=LockFile())
    runtime = LocalRuntime.from_bound_plan(bound, app)

    collected = [item async for item in runtime.invoke_stream("svc.stream", {"prompt": "a b c"})]
    assert collected == ["a", "b", "c"]


async def test_runtime_invoke_stream_unknown_raises_key_error() -> None:
    app = App("svc")
    env = Environment(name="local", target=Target.LOCAL)
    bound = app.plan(env, lock=LockFile())
    runtime = LocalRuntime.from_bound_plan(bound, app)

    with pytest.raises(KeyError, match=r"svc\.nope"):
        runtime.invoke_stream("svc.nope", {})


async def test_async_generator_function_skips_http_route() -> None:
    """Async generators register as streams only; no HTTP route is added."""
    app = App("svc")

    @app.expose()
    async def stream(prompt: str):
        yield prompt

    env = Environment(name="local", target=Target.LOCAL)
    bound = app.plan(env, lock=LockFile())
    runtime = LocalRuntime.from_bound_plan(bound, app)

    assert "svc.stream" in runtime.state.invokable_streams
    assert "svc.stream" not in runtime.state.invokables
    assert [r.path for r in runtime.routes] == []


async def test_lifespan_binds_runtime_to_app() -> None:
    from starlette.testclient import TestClient

    app = App("svc")

    @app.expose()
    async def double(x: int) -> dict[str, int]:
        return {"x": x * 2}

    env = Environment(name="local", target=Target.LOCAL)
    bound = app.plan(env, lock=LockFile())
    runtime = LocalRuntime.from_bound_plan(bound, app)

    # Before the lifespan starts, `app.invoke(...)` cannot dispatch.
    with pytest.raises(RuntimeError, match="No active Skaal runtime"):
        await app.invoke(double, x=3)

    # Inside the lifespan, the runtime is bound and dispatch works.
    asgi = runtime.build_asgi()
    with TestClient(asgi):
        result = await app.invoke(double, x=3)
        assert result == {"x": 6}

    # Once the lifespan exits, the binding is released again.
    with pytest.raises(RuntimeError, match="No active Skaal runtime"):
        await app.invoke(double, x=3)
