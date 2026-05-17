"""Tests for `skaal apps {list,graph,validate}`."""

from __future__ import annotations

import io
import logging
from pathlib import Path
from textwrap import dedent

import pytest
from typer.testing import CliRunner

from skaal.cli.apps_cmd import app as apps_app


def _write_pyproject(tmp_path: Path, body: str) -> None:
    (tmp_path / "pyproject.toml").write_text(dedent(body))


def _capture_logs() -> tuple[io.StringIO, logging.Logger, list[logging.Handler], int]:
    stream = io.StringIO()
    logger = logging.getLogger("skaal")
    previous_handlers = list(logger.handlers)
    previous_level = logger.level
    logger.addHandler(logging.StreamHandler(stream))
    logger.setLevel(logging.INFO)
    return stream, logger, previous_handlers, previous_level


def _run_apps(args: list[str]) -> tuple[int, str]:
    stream, logger, previous_handlers, previous_level = _capture_logs()
    try:
        result = CliRunner().invoke(apps_app, args)
    finally:
        logger.handlers = previous_handlers
        logger.setLevel(previous_level)
    return result.exit_code, stream.getvalue()


def test_list_shows_declared_apps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_pyproject(
        tmp_path,
        """
        [tool.skaal]
        target = "gcp"

        [tool.skaal.apps.backend]
        module = "myproj.backend:app"

        [tool.skaal.apps.frontend]
        module     = "myproj.frontend:app"
        depends_on = ["backend"]
        """,
    )
    monkeypatch.chdir(tmp_path)

    code, output = _run_apps(["list"])
    assert code == 0, output
    assert "backend" in output
    assert "frontend" in output


def test_graph_ascii(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_pyproject(
        tmp_path,
        """
        [tool.skaal.apps.backend]
        module = "myproj.backend:app"

        [tool.skaal.apps.frontend]
        module     = "myproj.frontend:app"
        depends_on = ["backend"]
        """,
    )
    monkeypatch.chdir(tmp_path)

    code, output = _run_apps(["graph"])
    assert code == 0, output
    assert "backend" in output
    assert "frontend" in output
    assert "(backend)" in output  # frontend's deps rendered


def test_graph_dot_format(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_pyproject(
        tmp_path,
        """
        [tool.skaal.apps.backend]
        module = "myproj.backend:app"

        [tool.skaal.apps.frontend]
        module     = "myproj.frontend:app"
        depends_on = ["backend"]
        """,
    )
    monkeypatch.chdir(tmp_path)

    code, output = _run_apps(["graph", "--format", "dot"])
    assert code == 0, output
    assert "digraph skaal" in output
    assert '"backend" -> "frontend"' in output


def test_graph_mermaid_format(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_pyproject(
        tmp_path,
        """
        [tool.skaal.apps.backend]
        module = "myproj.backend:app"

        [tool.skaal.apps.frontend]
        module     = "myproj.frontend:app"
        depends_on = ["backend"]
        """,
    )
    monkeypatch.chdir(tmp_path)

    code, output = _run_apps(["graph", "--format", "mermaid"])
    assert code == 0, output
    assert "graph LR" in output
    assert "backend --> frontend" in output


def test_validate_reports_cycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_pyproject(
        tmp_path,
        """
        [tool.skaal.apps.a]
        module     = "x:a"
        depends_on = ["b"]

        [tool.skaal.apps.b]
        module     = "x:b"
        depends_on = ["a"]
        """,
    )
    monkeypatch.chdir(tmp_path)

    code, output = _run_apps(["validate"])
    assert code != 0
    combined = output.lower()
    assert "cycle" in combined or "cycle" in combined


def test_list_errors_when_no_apps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_pyproject(
        tmp_path,
        """
        [tool.skaal]
        target = "gcp"
        """,
    )
    monkeypatch.chdir(tmp_path)

    code, _ = _run_apps(["list"])
    assert code != 0
