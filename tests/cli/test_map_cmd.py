"""Smoke tests for `skaal map`."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skaal.api import ResourceMap
from skaal.cli.main import app as cli_app

runner = CliRunner()


_FIXTURE = textwrap.dedent(
    """
    from skaal import App, Store


    app = App("map-fixture")


    @app.storage()
    class Sessions(Store[dict]):
        pass


    @app.function()
    async def greet(name: str) -> dict[str, str]:
        return {"hello": name}
    """
)


@pytest.fixture
def fixture_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    pkg_dir = tmp_path / "map_fixture_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    (pkg_dir / "app.py").write_text(_FIXTURE)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    sys.modules.pop("map_fixture_pkg", None)
    sys.modules.pop("map_fixture_pkg.app", None)
    return "map_fixture_pkg.app:app"


def test_map_renders_tree_and_writes_json(fixture_app: str, tmp_path: Path) -> None:
    result = runner.invoke(cli_app, ["map", fixture_app])
    assert result.exit_code == 0, result.output
    assert "map-fixture" in result.output
    assert "store" in result.output
    assert "function" in result.output
    assert "Wrote" in result.output

    payload = (tmp_path / ".skaal" / "map.json").read_text(encoding="utf-8")
    resource_map = ResourceMap.model_validate_json(payload)
    assert resource_map.app == "map-fixture"
    assert {entry.kind.value for entry in resource_map.resources} == {"store", "function"}


def test_map_respects_custom_output_path(fixture_app: str, tmp_path: Path) -> None:
    custom = tmp_path / "custom" / "resource-map.json"
    result = runner.invoke(cli_app, ["map", fixture_app, "--out", str(custom)])
    assert result.exit_code == 0, result.output
    assert custom.exists()


def test_map_reports_no_resources_for_empty_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pkg_dir = tmp_path / "empty_map_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    (pkg_dir / "app.py").write_text("from skaal import App\napp = App('empty-map')\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    sys.modules.pop("empty_map_pkg", None)
    sys.modules.pop("empty_map_pkg.app", None)

    result = runner.invoke(cli_app, ["map", "empty_map_pkg.app:app"])
    assert result.exit_code == 0, result.output
    assert "No resources discovered." in result.output

    payload = (tmp_path / ".skaal" / "map.json").read_text(encoding="utf-8")
    resource_map = ResourceMap.model_validate_json(payload)
    assert resource_map.resources == ()
