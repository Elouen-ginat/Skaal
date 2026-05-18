"""Smoke tests for `skaal where`."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skaal.api import _where
from skaal.cli.main import app as cli_app

runner = CliRunner()


_FIXTURE = textwrap.dedent(
    """
    from skaal import App, Store


    app = App("where-fixture")


    @app.storage()
    class Sessions(Store[dict]):
        pass
    """
)


@pytest.fixture
def fixture_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    pkg_dir = tmp_path / "where_fixture_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    (pkg_dir / "app.py").write_text(_FIXTURE)
    (tmp_path / "skaal.toml").write_text(
        "[env.prod]\ntarget = 'aws'\nregion = 'us-east-1'\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    sys.modules.pop("where_fixture_pkg", None)
    sys.modules.pop("where_fixture_pkg.app", None)
    return "where_fixture_pkg.app:app"


def test_where_renders_console_url(fixture_app: str, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_state = {
        "resources": [
            {
                "type": "aws:dynamodb/table:Table",
                "outputs": {
                    "name": "skaal-sessions",
                    "id": "skaal-sessions",
                    "tags": {
                        "skaal:resource_id": "where_fixture_pkg.app:Sessions",
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

    result = runner.invoke(
        cli_app,
        ["where", "where_fixture_pkg.app:Sessions", fixture_app],
    )

    assert result.exit_code == 0, result.output
    assert "where_fixture_pkg.app:Sessions" in result.output
    assert "aws:dynamodb/table:Table" in result.output
    assert "https://us-east-1.console.aws.amazon.com/dynamodbv2/home" in result.output


def test_where_rejects_unknown_resource(fixture_app: str) -> None:
    result = runner.invoke(cli_app, ["where", "missing-resource", fixture_app])

    assert result.exit_code != 0
    assert "Could not resolve" in result.output
