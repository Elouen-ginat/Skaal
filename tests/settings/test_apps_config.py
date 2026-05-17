"""Tests for [tool.skaal.apps] config parsing and `for_app` resolution."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from skaal.settings import SkaalSettings
from skaal.types.project import build_project_graph


def _write_pyproject(tmp_path: Path, body: str) -> None:
    (tmp_path / "pyproject.toml").write_text(dedent(body))


def test_apps_table_loads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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

    cfg = SkaalSettings()
    assert set(cfg.apps) == {"backend", "frontend"}
    assert cfg.apps["frontend"].depends_on == ["backend"]
    assert cfg.apps["backend"].module == "myproj.backend:app"


def test_for_app_inherits_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_pyproject(
        tmp_path,
        """
        [tool.skaal]
        target = "gcp"
        region = "europe-west1"

        [tool.skaal.apps.backend]
        module = "myproj.backend:app"
        """,
    )
    monkeypatch.chdir(tmp_path)

    resolved = SkaalSettings().for_app("backend")
    assert resolved.target == "gcp"
    assert resolved.region == "europe-west1"


def test_for_app_overrides_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_pyproject(
        tmp_path,
        """
        [tool.skaal]
        target = "gcp"
        region = "europe-west1"

        [tool.skaal.apps.backend]
        module = "myproj.backend:app"
        target = "aws"
        region = "us-east-1"
        """,
    )
    monkeypatch.chdir(tmp_path)

    resolved = SkaalSettings().for_app("backend")
    assert resolved.target == "aws"
    assert resolved.region == "us-east-1"


def test_for_app_unknown_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_pyproject(
        tmp_path,
        """
        [tool.skaal.apps.backend]
        module = "myproj.backend:app"
        """,
    )
    monkeypatch.chdir(tmp_path)

    with pytest.raises(KeyError, match="frontend"):
        SkaalSettings().for_app("frontend")


def test_app_module_required(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An apps entry without ``module`` is rejected at load time."""
    _write_pyproject(
        tmp_path,
        """
        [tool.skaal.apps.broken]
        target = "gcp"
        """,
    )
    monkeypatch.chdir(tmp_path)

    with pytest.raises(Exception, match=r"module"):
        SkaalSettings()


def test_unknown_app_field_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_pyproject(
        tmp_path,
        """
        [tool.skaal.apps.broken]
        module = "x:y"
        regionn = "oops"
        """,
    )
    monkeypatch.chdir(tmp_path)

    with pytest.raises(Exception):
        SkaalSettings()


# ── ProjectGraph ──────────────────────────────────────────────────────────────


def test_graph_topological_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_pyproject(
        tmp_path,
        """
        [tool.skaal.apps.frontend]
        module     = "myproj.frontend:app"
        depends_on = ["backend"]

        [tool.skaal.apps.backend]
        module = "myproj.backend:app"
        """,
    )
    monkeypatch.chdir(tmp_path)

    graph = build_project_graph(SkaalSettings())
    assert graph.order == ("backend", "frontend")
    assert graph.edges["frontend"] == frozenset({"backend"})
    assert graph.edges["backend"] == frozenset()


def test_graph_default_expose_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_pyproject(
        tmp_path,
        """
        [tool.skaal.apps.payment-api]
        module = "myproj.pay:app"
        """,
    )
    monkeypatch.chdir(tmp_path)

    graph = build_project_graph(SkaalSettings())
    assert graph.apps["payment-api"].expose == "SKAAL_APPREF_PAYMENT_API_URL"


def test_graph_explicit_expose(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_pyproject(
        tmp_path,
        """
        [tool.skaal.apps.backend]
        module = "myproj.backend:app"
        expose = "BACKEND_URL"
        """,
    )
    monkeypatch.chdir(tmp_path)

    graph = build_project_graph(SkaalSettings())
    assert graph.apps["backend"].expose == "BACKEND_URL"


def test_graph_cycle_detected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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

    with pytest.raises(ValueError, match="Cycle"):
        build_project_graph(SkaalSettings())


def test_graph_undeclared_dependency(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_pyproject(
        tmp_path,
        """
        [tool.skaal.apps.frontend]
        module     = "myproj.frontend:app"
        depends_on = ["nope"]
        """,
    )
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match="undeclared"):
        build_project_graph(SkaalSettings())


def test_graph_per_app_artifact_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When ``out`` is not set per-app, it defaults to ``<base.out>/<name>``."""
    _write_pyproject(
        tmp_path,
        """
        [tool.skaal]
        out = "artifacts"

        [tool.skaal.apps.backend]
        module = "myproj.backend:app"

        [tool.skaal.apps.frontend]
        module     = "myproj.frontend:app"
        out        = "build/frontend"
        depends_on = ["backend"]
        """,
    )
    monkeypatch.chdir(tmp_path)

    graph = build_project_graph(SkaalSettings())
    assert graph.apps["backend"].out == Path("artifacts/backend")
    assert graph.apps["frontend"].out == Path("build/frontend")


def test_graph_expose_env_for(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_pyproject(
        tmp_path,
        """
        [tool.skaal.apps.backend]
        module = "myproj.backend:app"
        expose = "BACKEND_URL"

        [tool.skaal.apps.frontend]
        module     = "myproj.frontend:app"
        depends_on = ["backend"]
        """,
    )
    monkeypatch.chdir(tmp_path)

    graph = build_project_graph(SkaalSettings())
    assert graph.expose_env_for("frontend") == {"BACKEND_URL": "backend"}
    assert graph.expose_env_for("backend") == {}


def test_graph_empty_when_no_apps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_pyproject(
        tmp_path,
        """
        [tool.skaal]
        target = "gcp"
        """,
    )
    monkeypatch.chdir(tmp_path)

    graph = build_project_graph(SkaalSettings())
    assert graph.apps == {}
    assert graph.order == ()
