"""Tests for the CLI-parity `skaal.api` module."""

from __future__ import annotations

import importlib
import sys
import textwrap
from pathlib import Path
from typing import Any, cast

import pytest

from skaal import api
from skaal.api import _where
from skaal.app import App
from skaal.binding.model import Target
from skaal.cli._load import AppSpec
from skaal.inference.model import ResourceKind
from skaal.plugins import Plugin, PluginRegistry

_FIXTURE = textwrap.dedent(
    """
    from skaal import App, Store


    app = App("api-fixture")


    @app.storage()
    class Sessions(Store[dict]):
        pass


    @app.expose()
    async def greet(name: str) -> dict[str, str]:
        return {"hello": name}
    """
)


_SKAAL_TOML = textwrap.dedent(
    """
    [env.local]
    target = "local"

    [env.prod]
    target = "aws"
    region = "us-east-1"
    """
).lstrip()


@pytest.fixture
def fixture_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, App]:
    pkg_dir = tmp_path / "api_fixture_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    (pkg_dir / "app.py").write_text(_FIXTURE)
    (tmp_path / "skaal.toml").write_text(_SKAAL_TOML)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    sys.modules.pop("api_fixture_pkg", None)
    sys.modules.pop("api_fixture_pkg.app", None)
    module = importlib.import_module("api_fixture_pkg.app")
    try:
        yield "api_fixture_pkg.app:app", cast(App, module.app)
    finally:
        sys.modules.pop("api_fixture_pkg", None)
        sys.modules.pop("api_fixture_pkg.app", None)


def test_plan_accepts_reference_and_returns_diff(fixture_app: tuple[str, App]) -> None:
    target, _ = fixture_app

    diff = api.plan(target)

    assert diff.bound.app == "api-fixture"
    assert [change.action for change in diff.changes] == ["create", "create"]


def test_render_plan_diff_markdown_returns_github_table(fixture_app: tuple[str, App]) -> None:
    target, _ = fixture_app

    markdown = api.render_plan_diff_markdown(api.plan(target))

    assert "| Action | Resource | Kind | Backend | Region | Details |" in markdown
    assert "`api_fixture_pkg.app:Sessions`" in markdown
    assert "- app: `api-fixture`" in markdown


def test_diff_bound_plans_reports_structural_changes(
    fixture_app: tuple[str, App], tmp_path: Path
) -> None:
    target, _ = fixture_app
    baseline = api.plan(target).bound

    app_file = tmp_path / "api_fixture_pkg" / "app.py"
    app_file.write_text(
        textwrap.dedent(
            """
            from skaal import App, Store


            app = App("api-fixture")


            @app.storage()
            class Sessions(Store[dict]):
                pass


            @app.expose()
            async def greet(name: str) -> dict[str, str]:
                return {"hello": name}


            @app.storage()
            class Tokens(Store[dict]):
                pass
            """
        )
    )
    sys.modules.pop("api_fixture_pkg.app", None)

    current = api.plan(target).bound
    diff = api.diff_bound_plans(current, baseline)

    assert [change.action for change in diff.changes] == ["create"]
    assert diff.changes[0].resource_id == "api_fixture_pkg.app:Tokens"


def test_map_accepts_app_object_and_writes_json(
    fixture_app: tuple[str, App], tmp_path: Path
) -> None:
    _, app = fixture_app
    out_path = tmp_path / "artefacts" / "map.json"

    resource_map = api.resources(app, out_path=out_path)

    assert resource_map.app == "api-fixture"
    assert out_path.exists()
    assert "greet" in out_path.read_text(encoding="utf-8")


def test_trace_resolves_log_line(fixture_app: tuple[str, App]) -> None:
    target, _ = fixture_app

    hit = api.find_source("error resource=api_fixture_pkg.app:greet", target)

    assert hit.resource.inferred.id == "api_fixture_pkg.app:greet"
    assert hit.resource.inferred.source.qualname == "greet"


def test_trace_rejects_unknown_resource(fixture_app: tuple[str, App]) -> None:
    target, _ = fixture_app

    with pytest.raises(ValueError, match="Could not resolve"):
        api.find_source("missing-resource", target)


def test_where_resolves_resource_console_url(
    fixture_app: tuple[str, App], monkeypatch: pytest.MonkeyPatch
) -> None:
    target, _ = fixture_app

    fake_state = {
        "resources": [
            {
                "type": "aws:dynamodb/table:Table",
                "outputs": {
                    "name": "skaal-sessions",
                    "id": "skaal-sessions",
                    "tags": {
                        "skaal:resource_id": "api_fixture_pkg.app:Sessions",
                    },
                },
            }
        ]
    }

    monkeypatch.setattr(
        _where,
        "_load_stack_deployment",
        lambda bound, env, stack_name: fake_state,
    )

    hit = api.locate("api_fixture_pkg.app:Sessions", target)

    assert hit.resource.inferred.id == "api_fixture_pkg.app:Sessions"
    assert hit.provider_type == "aws:dynamodb/table:Table"
    assert hit.physical_id == "skaal-sessions"
    assert "dynamodbv2" in hit.console_url


def test_where_rejects_unknown_resource(fixture_app: tuple[str, App]) -> None:
    target, _ = fixture_app

    with pytest.raises(ValueError, match="Could not resolve"):
        api.locate("missing-resource", target)


def test_where_builtin_target_metadata_survives_reset(
    fixture_app: tuple[str, App], monkeypatch: pytest.MonkeyPatch
) -> None:
    target, _ = fixture_app
    from skaal.plugins import _reset_for_tests as reset_plugins

    fake_state = {
        "resources": [
            {
                "type": "aws:dynamodb/table:Table",
                "outputs": {
                    "name": "built-in-store",
                    "id": "built-in-store",
                    "tags": {
                        "skaal:resource_id": "api_fixture_pkg.app:Sessions",
                    },
                },
            }
        ]
    }

    reset_plugins()
    _where._reset_for_tests()
    monkeypatch.setattr(
        _where,
        "_load_stack_deployment",
        lambda bound, env, stack_name: fake_state,
    )

    try:
        hit = api.locate("api_fixture_pkg.app:Sessions", target)
    finally:
        reset_plugins()
        _where._reset_for_tests()

    assert hit.provider_type == "aws:dynamodb/table:Table"
    assert hit.console_url.endswith("#table?name=built-in-store")


class _WherePlugin(Plugin):
    name = "where-plugin"

    def register(self, registry: PluginRegistry) -> None:
        registry.add_where_resource_preference(
            Target.AWS,
            ResourceKind.STORE,
            "aws:custom/service:Thing",
        )
        registry.add_where_console_url(
            Target.AWS,
            "aws:custom/service:Thing",
            lambda outputs, region: (
                f"https://plugins.example.test/{outputs['id']}?region={region or 'missing'}"
            ),
        )


class _FakeWhereEntryPoint:
    def __init__(self, name: str, plugin_type: type[Plugin]) -> None:
        self.name = name
        self._plugin_type = plugin_type

    def load(self) -> type[Plugin]:
        return self._plugin_type


def _where_plugin_state(*, include_builtin_candidate: bool = False) -> dict[str, object]:
    resources: list[dict[str, object]] = []
    if include_builtin_candidate:
        resources.append(
            {
                "type": "aws:dynamodb/table:Table",
                "outputs": {
                    "name": "built-in-store",
                    "id": "built-in-store",
                    "tags": {
                        "skaal:resource_id": "api_fixture_pkg.app:Sessions",
                    },
                },
            }
        )
    resources.append(
        {
            "type": "aws:custom/service:Thing",
            "outputs": {
                "id": "plugin-store",
                "tags": {
                    "skaal:resource_id": "api_fixture_pkg.app:Sessions",
                },
            },
        }
    )
    return {"resources": resources}


def _where_plugin_entry_points(
    group: str | None = None,
    **_: object,
) -> tuple[_FakeWhereEntryPoint, ...]:
    if group == "skaal.plugins":
        return (_FakeWhereEntryPoint("where-plugin", _WherePlugin),)
    return ()


def test_where_loads_plugin_contributed_resolver(
    fixture_app: tuple[str, App], monkeypatch: pytest.MonkeyPatch
) -> None:
    target, _ = fixture_app
    from skaal.plugins import _reset_for_tests as reset_plugins

    reset_plugins()
    _where._reset_for_tests()
    monkeypatch.setattr("importlib.metadata.entry_points", _where_plugin_entry_points)
    monkeypatch.setattr(
        _where,
        "_load_stack_deployment",
        lambda bound, env, stack_name: _where_plugin_state(),
    )

    try:
        hit = api.locate("api_fixture_pkg.app:Sessions", target)
    finally:
        reset_plugins()
        _where._reset_for_tests()

    assert hit.provider_type == "aws:custom/service:Thing"
    assert hit.physical_id == "plugin-store"
    assert hit.console_url == "https://plugins.example.test/plugin-store?region=us-east-1"


def test_where_plugin_resolver_handles_missing_region(
    fixture_app: tuple[str, App], monkeypatch: pytest.MonkeyPatch
) -> None:
    target, _ = fixture_app
    from skaal.binding.model import Environment
    from skaal.plugins import _reset_for_tests as reset_plugins

    reset_plugins()
    _where._reset_for_tests()
    monkeypatch.setattr("importlib.metadata.entry_points", _where_plugin_entry_points)
    monkeypatch.setattr(
        _where,
        "_load_stack_deployment",
        lambda bound, env, stack_name: _where_plugin_state(),
    )

    try:
        hit = _where.resolve_where(
            "api_fixture_pkg.app:Sessions",
            api.plan(target).bound,
            Environment(name="prod", target=Target.AWS, region=None),
        )
    finally:
        reset_plugins()
        _where._reset_for_tests()

    assert hit.console_url == "https://plugins.example.test/plugin-store?region=missing"


def test_where_plugin_preference_beats_builtin_candidate(
    fixture_app: tuple[str, App], monkeypatch: pytest.MonkeyPatch
) -> None:
    target, _ = fixture_app
    from skaal.plugins import _reset_for_tests as reset_plugins

    reset_plugins()
    _where._reset_for_tests()
    monkeypatch.setattr("importlib.metadata.entry_points", _where_plugin_entry_points)
    monkeypatch.setattr(
        _where,
        "_load_stack_deployment",
        lambda bound, env, stack_name: _where_plugin_state(include_builtin_candidate=True),
    )

    try:
        hit = api.locate("api_fixture_pkg.app:Sessions", target)
    finally:
        reset_plugins()
        _where._reset_for_tests()

    assert hit.provider_type == "aws:custom/service:Thing"
    assert hit.physical_id == "plugin-store"


def test_build_accepts_reference_and_returns_manifest(fixture_app: tuple[str, App]) -> None:
    target, _ = fixture_app

    result = api.build(target, env_name="prod")

    assert result.manifest.app == "api-fixture"
    assert result.manifest.target.value == "aws"
    assert result.build_dir.name == "prod"
    assert result.app_spec == AppSpec.parse(target)


def test_deploy_returns_lock_update_without_pulumi(
    fixture_app: tuple[str, App], monkeypatch: pytest.MonkeyPatch
) -> None:
    target, _ = fixture_app

    calls: list[tuple[bool, bool]] = []

    def fake_run_pulumi(**kwargs: Any) -> None:
        calls.append((bool(kwargs["preview"]), bool(kwargs["yes"])))

    monkeypatch.setattr("skaal.api._commands._run_pulumi", fake_run_pulumi)

    result = api.deploy(target, env_name="prod", preview=True, yes=True)

    assert result.preview is True
    assert result.lock_updated is True
    assert ("prod", "api_fixture_pkg.app:Sessions") in result.lock.entries
    assert calls == [(True, True)]


def test_doctor_reports_local_environment() -> None:
    report = api.doctor()

    assert report.python_version
    assert report.skaal_version


def test_init_matches_cli_not_implemented_error() -> None:
    with pytest.raises(NotImplementedError, match="not yet implemented"):
        api.init()


def test_run_builds_runtime_and_serves(
    fixture_app: tuple[str, App], monkeypatch: pytest.MonkeyPatch
) -> None:
    import types

    target, app = fixture_app
    called: dict[str, object] = {}

    class FakeRuntime:
        def serve(self, *, host: str, port: int) -> None:
            called["host"] = host
            called["port"] = port

    class FakeLocalRuntime:
        @staticmethod
        def from_bound_plan(bound: object, skaal_app: object) -> FakeRuntime:
            called["bound"] = bound
            called["app"] = skaal_app
            return FakeRuntime()

    monkeypatch.setitem(
        sys.modules,
        "skaal.runtime",
        types.SimpleNamespace(LocalRuntime=FakeLocalRuntime),
    )

    api.run(target, host="0.0.0.0", port=9000)

    assert called["app"] is app
    assert called["host"] == "0.0.0.0"
    assert called["port"] == 9000


def test_stubs_emits_stub_package(fixture_app: tuple[str, App], tmp_path: Path) -> None:
    target, _ = fixture_app
    out_dir = tmp_path / "api_fixture_stubs"

    result = api.stubs(target, out_dir, package_name="api_fixture_stubs")

    assert result.package_name == "api_fixture_stubs"
    assert result.out_dir == out_dir.resolve()
    assert result.manifest.package_name == "api_fixture_stubs"
    assert (out_dir / "__init__.pyi").exists()
