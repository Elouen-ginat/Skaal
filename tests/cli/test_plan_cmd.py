"""Smoke tests for `skaal plan`."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skaal.cli.main import app

runner = CliRunner()


_FIXTURE = textwrap.dedent(
    """
    from skaal import App, Store


    app = App("plan-fixture")


    @app.storage()
    class Sessions(Store[dict]):
        pass
    """
)


@pytest.fixture
def fixture_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    pkg_dir = tmp_path / "plan_fixture_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    (pkg_dir / "app.py").write_text(_FIXTURE)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    sys.modules.pop("plan_fixture_pkg", None)
    sys.modules.pop("plan_fixture_pkg.app", None)
    return "plan_fixture_pkg.app:app"


def test_plan_renders_bound_plan_table(fixture_app: str) -> None:
    result = runner.invoke(app, ["plan", fixture_app])
    assert result.exit_code == 0, result.output
    assert "plan-fixture" in result.output
    assert "Sessions" in result.output
    # The default `local` env binds STOREs to sqlite via the defaults table.
    assert "sqlite" in result.output


def test_plan_reports_no_resources_for_empty_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pkg_dir = tmp_path / "empty_app_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    (pkg_dir / "app.py").write_text("from skaal import App\napp = App('empty')\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    sys.modules.pop("empty_app_pkg", None)
    sys.modules.pop("empty_app_pkg.app", None)

    result = runner.invoke(app, ["plan", "empty_app_pkg.app:app"])
    assert result.exit_code == 0, result.output
    assert "No resources discovered." in result.output
