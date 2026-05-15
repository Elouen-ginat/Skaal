"""End-to-end tests for `skaal.inference.walk.infer`."""

from __future__ import annotations

from skaal import App, BlobStore, Channel, Module, Store, infer
from skaal.inference import InferredPlan, ResourceKind


def test_empty_app_yields_empty_resource_tuple() -> None:
    app = App("empty")
    plan = infer(app)
    assert isinstance(plan, InferredPlan)
    assert plan.app == "empty"
    assert plan.resources == ()
    assert plan.edges == ()
    assert plan.fingerprint != ""


def test_storage_function_job_channel_schedule_are_recognised() -> None:
    from skaal import Every

    app = App("demo")

    @app.storage()
    class Users(Store[dict]):
        pass

    @app.storage(kind="blob")
    class Assets(BlobStore):
        pass

    @app.function()
    async def signup(uid: str) -> str:
        return uid

    @app.job()
    async def reindex() -> None: ...

    @app.channel()
    class Events(Channel[dict]):  # type: ignore[type-arg]
        pass

    @app.schedule(trigger=Every(interval="60s"))
    async def heartbeat() -> None: ...

    plan = infer(app)
    kinds = sorted(r.kind.value for r in plan.resources)
    assert kinds == [
        "blob",
        "channel",
        "function",
        "job",
        "schedule",
        "store",
    ]


def test_resource_ids_follow_module_qualname_convention() -> None:
    app = App("demo")

    @app.storage()
    class Users(Store[dict]):
        pass

    plan = infer(app)
    ids = {r.id for r in plan.resources}
    # ID is `<module>:<qualname>` — the qualname for a class defined inside a
    # test function includes the function name and `<locals>`, so we only
    # assert the module/qualname separator and final identifier.
    assert any(":" in rid and rid.endswith("Users") for rid in ids)


def test_submodule_resources_are_collected() -> None:
    inner = Module("inner")

    @inner.storage()
    class Inner(Store[dict]):
        pass

    app = App("outer")
    app.use(inner)

    plan = infer(app)
    assert any(r.kind is ResourceKind.STORE and "Inner" in r.id for r in plan.resources)


def test_path_mount_emits_asgi_service_resource() -> None:
    app = App("demo")
    app.mount("/api", _DummyAsgiApp())

    plan = infer(app)
    asgi_resources = [r for r in plan.resources if r.kind is ResourceKind.ASGI_SERVICE]
    assert len(asgi_resources) == 1
    assert asgi_resources[0].overrides.options.get("path") == "/api"


class _DummyAsgiApp:
    async def __call__(self, scope: object, receive: object, send: object) -> None:
        return None


def test_no_mount_no_asgi_service_resource() -> None:
    app = App("demo")
    plan = infer(app)
    assert not any(r.kind is ResourceKind.ASGI_SERVICE for r in plan.resources)


def test_inferred_plan_round_trips_through_json() -> None:
    app = App("demo")

    @app.storage()
    class Users(Store[dict]):
        pass

    plan = infer(app)
    payload = plan.model_dump_json(by_alias=True)
    assert InferredPlan.model_validate_json(payload) == plan


def test_app_infer_method_matches_module_function() -> None:
    app = App("demo")

    @app.storage()
    class Users(Store[dict]):
        pass

    assert app.infer() == infer(app)
