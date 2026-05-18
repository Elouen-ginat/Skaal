"""Smoke tests for `skaal plan`."""

from __future__ import annotations

import sys
import textwrap
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skaal.binding.model import LockEntry, LockFile
from skaal.cli._load import load_app, load_plan
from skaal.cli.main import app

runner = CliRunner()


def _make_fixture_app_source(app_name: str = "plan-fixture") -> str:
    return textwrap.dedent(
        f"""
        from skaal import App, Store


        app = App("{app_name}")


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
    (pkg_dir / "app.py").write_text(_make_fixture_app_source())
    monkeypatch.syspath_prepend(str(tmp_path))  # pyright: ignore[reportUnknownMemberType]
    monkeypatch.chdir(tmp_path)
    sys.modules.pop("plan_fixture_pkg", None)
    sys.modules.pop("plan_fixture_pkg.app", None)
    return "plan_fixture_pkg.app:app"


def test_plan_renders_bound_plan_table(fixture_app: str) -> None:
    result = runner.invoke(app, ["plan", fixture_app])
    assert result.exit_code == 0, result.output
    assert "plan-fixture" in result.output
    assert "create" in result.output
    assert "store" in result.output
    assert "sqlite" in result.output


def test_plan_reports_no_resources_for_empty_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pkg_dir = tmp_path / "empty_app_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    (pkg_dir / "app.py").write_text("from skaal import App\napp = App('empty')\n")
    monkeypatch.syspath_prepend(str(tmp_path))  # pyright: ignore[reportUnknownMemberType]
    monkeypatch.chdir(tmp_path)
    sys.modules.pop("empty_app_pkg", None)
    sys.modules.pop("empty_app_pkg.app", None)

    result = runner.invoke(app, ["plan", "empty_app_pkg.app:app"])
    assert result.exit_code == 0, result.output
    assert "No resources discovered." in result.output


def test_plan_reports_no_changes_when_lock_matches(fixture_app: str, tmp_path: Path) -> None:
    skaal_app = load_app(fixture_app)
    bound = load_plan(skaal_app, "local").bound
    lock = LockFile(
        entries={
            ("local", resource.inferred.id): LockEntry(
                backend=resource.backend,
                region=resource.region,
                pinned_at=datetime.now(UTC),
                pinned_by="test",
                fingerprint=bound.bound_fingerprint,
            )
            for resource in bound.resources
            if not resource.external
        }
    )
    lock.save(tmp_path / "skaal.lock")

    result = runner.invoke(app, ["plan", fixture_app])
    assert result.exit_code == 0, result.output
    assert "No changes." in result.output
    assert "create" not in result.output
    assert "update" not in result.output


def test_plan_reports_updates_when_code_changes_after_lock(
    fixture_app: str, tmp_path: Path
) -> None:
    skaal_app = load_app(fixture_app)
    bound = load_plan(skaal_app, "local").bound
    lock = LockFile(
        entries={
            ("local", resource.inferred.id): LockEntry(
                backend=resource.backend,
                region=resource.region,
                pinned_at=datetime.now(UTC),
                pinned_by="test",
                fingerprint=bound.bound_fingerprint,
            )
            for resource in bound.resources
            if not resource.external
        }
    )
    lock.save(tmp_path / "skaal.lock")

    app_file = tmp_path / "plan_fixture_pkg" / "app.py"
    app_file.write_text(_make_fixture_app_source("plan-fixture-v2"))
    sys.modules.pop("plan_fixture_pkg.app", None)

    result = runner.invoke(app, ["plan", fixture_app])
    assert result.exit_code == 0, result.output
    assert "update" in result.output
    assert "fingerprint" in result.output


def test_plan_renders_github_markdown(fixture_app: str) -> None:
    result = runner.invoke(app, ["plan", fixture_app, "--format", "github-markdown"])

    assert result.exit_code == 0, result.output
    assert "| Action | Resource | Kind | Backend | Region | Details |" in result.output
    assert "`plan_fixture_pkg.app:Sessions`" in result.output
    assert "- env: `local`" in result.output


def test_plan_uses_pyproject_app_and_default_environment(
    fixture_app: str,
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            f"""
            [tool.skaal]
            app = "{fixture_app}"
            default_environment = "dev"
            lock = "custom.lock"
            """
        ).lstrip(),
        encoding="utf-8",
    )
    (tmp_path / "skaal.toml").write_text(
        textwrap.dedent(
            """
            [defaults]
            target = "local"

            [env.dev]
            region = "eu-west-1"
            """
        ).lstrip(),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["plan"])

    assert result.exit_code == 0, result.output
    assert "plan-fixture" in result.output
