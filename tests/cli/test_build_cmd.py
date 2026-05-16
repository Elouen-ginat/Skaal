"""Smoke tests for `skaal build`."""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skaal.cli.main import app as cli_app

runner = CliRunner()


_FIXTURE = textwrap.dedent(
    """
    from skaal import App


    app = App("build-fixture")


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
def fixture_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    pkg_dir = tmp_path / "build_fixture_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    (pkg_dir / "app.py").write_text(_FIXTURE)
    (tmp_path / "skaal.toml").write_text(_SKAAL_TOML)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    sys.modules.pop("build_fixture_pkg", None)
    sys.modules.pop("build_fixture_pkg.app", None)
    return "build_fixture_pkg.app:app"


def test_build_renders_artefacts_for_aws_env(fixture_app: str, tmp_path: Path) -> None:
    result = runner.invoke(cli_app, ["build", fixture_app, "--env", "prod"])
    assert result.exit_code == 0, result.output
    assert "Built" in result.output

    build_dir = tmp_path / ".skaal" / "build" / "prod"
    assert build_dir.is_dir()
    manifest = json.loads((build_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["app"] == "build-fixture"
    assert {r["kind"] for r in manifest["resources"]} == {"function"}


def test_build_fails_for_local_env(fixture_app: str) -> None:
    """`skaal build` only targets AWS in 0.4.0-alpha."""
    result = runner.invoke(cli_app, ["build", fixture_app, "--env", "local"])
    assert result.exit_code != 0
    assert "only supports target" in result.output or "aws" in result.output


def test_build_respects_custom_out_dir(fixture_app: str, tmp_path: Path) -> None:
    custom = tmp_path / "custom_out"
    result = runner.invoke(cli_app, ["build", fixture_app, "--env", "prod", "--out", str(custom)])
    assert result.exit_code == 0, result.output
    assert (custom / "manifest.json").exists()
