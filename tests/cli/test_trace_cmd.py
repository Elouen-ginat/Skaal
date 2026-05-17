"""Smoke tests for `skaal trace`."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skaal.cli.main import app as cli_app

runner = CliRunner()


_FIXTURE = textwrap.dedent(
    """
    from skaal import App, Store


    app = App("trace-fixture")


    @app.storage()
    class Sessions(Store[dict]):
        pass


    @app.expose()
    async def greet(name: str) -> dict[str, str]:
        return {"hello": name}
    """
)


@pytest.fixture
def fixture_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    pkg_dir = tmp_path / "trace_fixture_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    (pkg_dir / "app.py").write_text(_FIXTURE)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    sys.modules.pop("trace_fixture_pkg", None)
    sys.modules.pop("trace_fixture_pkg.app", None)
    return "trace_fixture_pkg.app:app"


def test_trace_resolves_exact_resource_id(fixture_app: str) -> None:
    result = runner.invoke(cli_app, ["trace", "trace_fixture_pkg.app:greet", fixture_app])
    assert result.exit_code == 0, result.output
    assert "trace-fixture" in result.output
    assert "trace_fixture_pkg.app:greet" in result.output
    assert "source" in result.output
    assert "app.py:" in result.output
    assert "trace_fixture_pkg.app:greet" in result.output


def test_trace_resolves_resource_id_embedded_in_log_line(fixture_app: str) -> None:
    line = "RuntimeError: resource_id='trace_fixture_pkg.app:greet' failed to resolve"
    result = runner.invoke(cli_app, ["trace", line, fixture_app])
    assert result.exit_code == 0, result.output
    assert "matched" in result.output
    assert "trace_fixture_pkg.app:greet" in result.output


def test_trace_rejects_unknown_input(fixture_app: str) -> None:
    result = runner.invoke(cli_app, ["trace", "missing-resource", fixture_app])
    assert result.exit_code != 0
    assert "Could not resolve" in result.output
