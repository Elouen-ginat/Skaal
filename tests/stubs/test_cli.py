"""Smoke tests for `skaal stubs` (ADR 033 §5.2)."""

from __future__ import annotations

import ast
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


    app = App("stubs-fixture")


    @app.storage
    class Sessions(Store[dict]):
        pass


    @app.function()
    async def hello(name: str) -> dict:
        return {"name": name}
    """
)


@pytest.fixture
def fixture_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, Path]:
    pkg_dir = tmp_path / "stubs_fixture_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    (pkg_dir / "app.py").write_text(_FIXTURE)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    sys.modules.pop("stubs_fixture_pkg", None)
    sys.modules.pop("stubs_fixture_pkg.app", None)
    return "stubs_fixture_pkg.app:app", tmp_path


def test_stubs_emits_package(fixture_app: tuple[str, Path]) -> None:
    spec, tmp_path = fixture_app
    out_dir = tmp_path / "out"
    result = runner.invoke(
        app,
        ["stubs", "--from", spec, "--to", str(out_dir), "--as", "stubs_fixture_stubs"],
    )
    assert result.exit_code == 0, result.output
    assert "stubs_fixture_stubs" in result.output

    assert (out_dir / "py.typed").exists()
    assert (out_dir / "_manifest.json").exists()
    init = (out_dir / "__init__.pyi").read_text()
    assert "Sessions" in init
    assert "hello" in init

    # Every emitted .pyi must parse as valid Python.
    for pyi in out_dir.glob("*.pyi"):
        ast.parse(pyi.read_text(), filename=str(pyi))


def test_stubs_uses_dir_basename_when_no_as_provided(
    fixture_app: tuple[str, Path],
) -> None:
    spec, tmp_path = fixture_app
    out_dir = tmp_path / "fallback_stubs"
    result = runner.invoke(app, ["stubs", "--from", spec, "--to", str(out_dir)])
    assert result.exit_code == 0, result.output
    assert "fallback_stubs" in result.output


def test_stubs_rejects_invalid_source(fixture_app: tuple[str, Path]) -> None:
    _, tmp_path = fixture_app
    result = runner.invoke(
        app,
        [
            "stubs",
            "--from",
            "nonexistent.module:app",
            "--to",
            str(tmp_path / "out"),
        ],
    )
    assert result.exit_code != 0
