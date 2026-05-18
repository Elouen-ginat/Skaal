"""Tests for late-bound synth registration on an existing `DeployTarget`.

Each test patches in a fake entry-point pointing at a plugin that adds
both a `BackendEntry` and a synth module to the AWS target. The test then
exercises `synthesize_stack(...)` to confirm the binder and the deploy
dispatcher both see the new backend.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any, ClassVar

import pytest

pulumi = pytest.importorskip("pulumi")
pytest.importorskip("pulumi_aws")
pytest.importorskip("pulumi_docker")

import skaal.deploy.aws  # noqa: E402 — side-effect import registers AWS target
from skaal import App, Backend, Target  # noqa: E402
from skaal.binding.model import Environment, LockFile  # noqa: E402
from skaal.binding.registry import BackendSpec  # noqa: E402
from skaal.deploy import (  # noqa: E402
    Plugin,
    PluginRegistry,
    SynthContext,
    SynthModule,
    SynthResult,
    SynthSpec,
    synthesize_stack,
)
from skaal.deploy.aws._config import AwsConfig  # noqa: E402


class _MyDatabase(Backend[object]):
    name = "my-database"
    kinds = frozenset({"store"})


class _MyDatabaseSynth(SynthModule[AwsConfig]):
    """Fake KV store synth (re-uses DynamoDB under the hood as a stand-in)."""

    SPEC: ClassVar[SynthSpec] = SynthSpec(
        tokens=(_MyDatabase,),
        description="Fake KV store for the plugin loader test.",
    )

    def synthesize(self, ctx: SynthContext[AwsConfig]) -> SynthResult:
        import pulumi_aws as aws

        table = aws.dynamodb.Table(
            ctx.pulumi_name,
            billing_mode="PAY_PER_REQUEST",
            hash_key="pk",
            attributes=[aws.dynamodb.TableAttributeArgs(name="pk", type="S")],
            tags=ctx.tags,
        )
        return SynthResult(resource_id=ctx.resource_id, primary=table)


class _MyDatabasePlugin(Plugin):
    name = "my-database"

    def register(self, registry: PluginRegistry) -> None:
        registry.add_backend(BackendSpec(token=_MyDatabase, targets=frozenset({Target.AWS})))
        registry.add_synth(Target.AWS, _MyDatabaseSynth)


class _FakeEntryPoint:
    def __init__(self, name: str, target: type[Plugin]) -> None:
        self.name = name
        self._target = target

    def load(self) -> Any:
        return self._target


class _Mocks(pulumi.runtime.Mocks):
    def new_resource(self, args: pulumi.runtime.MockResourceArgs) -> tuple[str, dict[str, Any]]:
        outputs = dict(args.inputs)
        outputs.setdefault("name", args.name)
        outputs.setdefault("arn", f"arn:aws:mock::{args.name}")
        return args.name + "-id", outputs

    def call(self, args: pulumi.runtime.MockCallArgs) -> dict[str, Any]:
        return {}


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch: pytest.MonkeyPatch) -> Iterable[None]:
    from skaal.binding.registry import _reset_for_tests as reset_binding
    from skaal.plugins import _reset_for_tests as reset_plugins

    reset_plugins()
    reset_binding()
    # Clear the AWS target's plugin-contributed synths (the lookup is
    # mutable and persists across tests).
    target = skaal.deploy.aws.TARGET
    builtin = set(target.supported_backends())
    pulumi.runtime.set_mocks(_Mocks(), preview=False)

    def fake_entry_points(group: str | None = None, **_: object) -> tuple[Any, ...]:
        if group == "skaal.plugins":
            return (_FakeEntryPoint("mydb", _MyDatabasePlugin),)
        return ()

    monkeypatch.setattr("importlib.metadata.entry_points", fake_entry_points)
    yield
    # Drop any extra synths we registered during the test (both halves
    # of the dispatch — `_synth` keyed by backend name and
    # `_synth_instances` keyed by the live instance).
    with target._synth_lock:
        for backend in list(target._synth):
            if backend not in builtin:
                del target._synth[backend]
                target._synth_instances.pop(backend, None)
    reset_plugins()
    reset_binding()


def test_plugin_adds_backend_and_synth_end_to_end(tmp_path: Path) -> None:
    """A plugin contributes both a binding entry and a deploy synth."""
    from skaal import Store, connect
    from skaal.deploy import AppSpec, build_artefacts

    app = App("svc")

    @connect(name="external-db")
    class MyData(Store[dict, _MyDatabase]):
        pass

    @app.expose()
    async def greet(name: str) -> dict[str, str]:
        return {"hello": name}

    env = Environment(name="prod", target=Target.AWS, region="us-east-1")
    bound = app.plan(env, lock=LockFile())
    build_dir = build_artefacts(bound, env, AppSpec.for_app(app), out_dir=tmp_path)

    results = synthesize_stack(bound, env, build_dir)
    # The MyData resource is external, so the synth driver skips it; the
    # `function` Lambda still synthesizes. The key assertion is that the
    # binder accepted the `my-database` backend at `bind()` time.
    assert any("greet" in rid for rid in results)


def test_plugin_synth_dispatches_for_non_external_resource(tmp_path: Path) -> None:
    """Plugin-contributed synth runs when a `Store` is pinned to it directly."""
    from skaal import Store
    from skaal.deploy import AppSpec, build_artefacts

    app = App("svc")

    @app.storage()
    class Cache(Store[dict, _MyDatabase]):
        pass

    @app.expose()
    async def hit(key: str) -> dict:
        return await Cache.get(key) or {}

    env = Environment(name="prod", target=Target.AWS, region="us-east-1")
    bound = app.plan(env, lock=LockFile())
    build_dir = build_artefacts(bound, env, AppSpec.for_app(app), out_dir=tmp_path)

    results = synthesize_stack(bound, env, build_dir)
    store_id = next(r for r in results if "Cache" in r)
    # The plugin synth used DynamoDB as a stand-in — assert on its class
    # name to prove we dispatched through the plugin path.
    assert results[store_id].primary.__class__.__name__ == "Table"
