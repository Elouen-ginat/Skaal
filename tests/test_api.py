"""Tests for the CLI-parity `skaal.api` module."""

from __future__ import annotations

import importlib
import sys
import textwrap
import types
from pathlib import Path
from typing import cast

import pytest

from skaal import api
from skaal.app import App
from skaal.cli._load import AppSpec

_FIXTURE = textwrap.dedent(
    """
    from skaal import App, Store


    app = App("api-fixture")


    @app.storage()
    class Sessions(Store[dict]):
        pass


    @app.function()
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


def test_map_accepts_app_object_and_writes_json(
    fixture_app: tuple[str, App], tmp_path: Path
) -> None:
    _, app = fixture_app
    out_path = tmp_path / "artefacts" / "map.json"

    resource_map = api.map(app, out_path=out_path)

    assert resource_map.app == "api-fixture"
    assert out_path.exists()
    assert "greet" in out_path.read_text(encoding="utf-8")


def test_trace_resolves_log_line(fixture_app: tuple[str, App]) -> None:
    target, _ = fixture_app

    hit = api.trace("error resource=api_fixture_pkg.app:greet", target)

    assert hit.resource.inferred.id == "api_fixture_pkg.app:greet"
    assert hit.resource.inferred.source.qualname == "greet"


def test_trace_rejects_unknown_resource(fixture_app: tuple[str, App]) -> None:
    target, _ = fixture_app

    with pytest.raises(ValueError, match="Could not resolve"):
        api.trace("missing-resource", target)


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

    def fake_run_pulumi(**kwargs: object) -> None:
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
