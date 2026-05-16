"""Tests for the CLI-parity `skaal.api` module."""

from __future__ import annotations

import importlib
import sys
import textwrap
from pathlib import Path
from typing import cast

import pytest

from skaal import api
from skaal.app import App

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


@pytest.fixture
def fixture_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, App]:
    pkg_dir = tmp_path / "api_fixture_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    (pkg_dir / "app.py").write_text(_FIXTURE)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    sys.modules.pop("api_fixture_pkg", None)
    sys.modules.pop("api_fixture_pkg.app", None)
    module = importlib.import_module("api_fixture_pkg.app")
    return "api_fixture_pkg.app:app", cast(App, module.app)


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
