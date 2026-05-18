"""Smoke tests for `skaal destroy`."""

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
    from skaal import App


    app = App("destroy-fixture")


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
def fixture_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    pkg_dir = tmp_path / "destroy_fixture_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
    (pkg_dir / "app.py").write_text(_FIXTURE, encoding="utf-8")
    (tmp_path / "skaal.toml").write_text(_SKAAL_TOML, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    sys.modules.pop("destroy_fixture_pkg", None)
    sys.modules.pop("destroy_fixture_pkg.app", None)
    return "destroy_fixture_pkg.app:app"


def test_destroy_fails_clean_when_pulumi_missing(
    fixture_app: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without the `deploy` extras, the verb surfaces a `MissingExtraError`."""
    import builtins

    real_import = builtins.__import__
    blocked = {"pulumi", "pulumi.automation", "pulumi_aws", "pulumi_docker"}

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name in blocked:
            raise ImportError(f"blocked: {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    result = runner.invoke(cli_app, ["destroy", fixture_app, "--env", "prod", "--yes"])
    assert result.exit_code != 0
    assert "skaal[deploy,aws]" in (result.output or "") or "Pulumi" in (result.output or "")


def test_destroy_rejects_local_env(fixture_app: str) -> None:
    """`skaal destroy --env local` fails before reaching Pulumi."""
    result = runner.invoke(cli_app, ["destroy", fixture_app, "--env", "local", "--yes"])
    assert result.exit_code != 0
