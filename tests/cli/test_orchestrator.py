"""Tests for the multi-app orchestrator (`skaal.cli._orchestrator`)."""

from __future__ import annotations

import os
from pathlib import Path
from textwrap import dedent
from typing import Any
from unittest.mock import patch

import pytest

from skaal.cli import _orchestrator
from skaal.project_lock import ProjectLock
from skaal.settings import SkaalSettings
from skaal.types.project import build_project_graph


def _write_pyproject(tmp_path: Path, body: str) -> None:
    (tmp_path / "pyproject.toml").write_text(dedent(body))


def _two_app_graph(tmp_path: Path):
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
    return build_project_graph(SkaalSettings())


def test_deploy_all_runs_in_topo_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    graph = _two_app_graph(tmp_path)

    calls: list[str] = []

    def fake_plan(*args: Any, **kwargs: Any) -> Any:
        calls.append(f"plan:{args[0]}")

        class P:
            pass

        return P()

    def fake_build(*args: Any, **kwargs: Any) -> list:
        calls.append(f"build:{kwargs.get('output_dir')}")
        return []

    def fake_deploy(**kwargs: Any) -> dict[str, str]:
        calls.append(f"deploy:{kwargs['artifacts_dir']}")
        # Return a Cloud-Run-like service URL; orchestrator picks this up.
        name = Path(str(kwargs["artifacts_dir"])).name
        return {"serviceUrl": f"https://{name}.run.app"}

    with (
        patch("skaal.api.plan", fake_plan),
        patch("skaal.api.build", fake_build),
        patch("skaal.api.deploy", fake_deploy),
    ):
        steps = _orchestrator.deploy_all(graph, lock_path=tmp_path / "lock.toml")

    # Backend before frontend.
    assert [s.name for s in steps] == ["backend", "frontend"]
    assert all(s.success for s in steps)
    assert steps[0].url == "https://backend.run.app"

    # The orchestrator must have injected the backend URL into the
    # frontend's environment by the time fake_deploy ran. We can verify
    # via the order of calls: backend's plan/build/deploy must precede
    # frontend's.
    backend_idx = next(i for i, c in enumerate(calls) if c.startswith("deploy:") and "backend" in c)
    frontend_idx = next(
        i for i, c in enumerate(calls) if c.startswith("deploy:") and "frontend" in c
    )
    assert backend_idx < frontend_idx


def test_deploy_all_writes_project_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    graph = _two_app_graph(tmp_path)

    with (
        patch("skaal.api.plan", lambda *a, **k: None),
        patch("skaal.api.build", lambda *a, **k: []),
        patch("skaal.api.deploy", lambda **k: {"serviceUrl": "https://x.run.app"}),
    ):
        _orchestrator.deploy_all(graph, lock_path=tmp_path / "project.lock")

    lock = ProjectLock.read(tmp_path / "project.lock")
    assert "backend" in lock.apps
    assert "frontend" in lock.apps
    assert lock.apps["frontend"].depends_on == ["backend"]
    assert lock.apps["frontend"].last_url == "https://x.run.app"


def test_deploy_all_aborts_on_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    graph = _two_app_graph(tmp_path)

    def fake_deploy(**kwargs: Any) -> dict[str, str]:
        if "backend" in str(kwargs["artifacts_dir"]):
            raise RuntimeError("backend boom")
        return {"serviceUrl": "https://frontend.run.app"}

    with (
        patch("skaal.api.plan", lambda *a, **k: None),
        patch("skaal.api.build", lambda *a, **k: []),
        patch("skaal.api.deploy", fake_deploy),
    ):
        steps = _orchestrator.deploy_all(graph, lock_path=tmp_path / "p.lock")

    assert len(steps) == 1
    assert steps[0].name == "backend"
    assert not steps[0].success
    assert "backend boom" in (steps[0].error or "")


def test_hydrate_env_from_lock_injects_upstream_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    graph = _two_app_graph(tmp_path)
    lock = ProjectLock()
    lock.upsert(
        "backend",
        module="myproj.backend:app",
        target="gcp",
        last_url="https://backend.run.app",
    )
    lock_path = tmp_path / "project.lock"
    lock.write(lock_path)

    monkeypatch.delenv("SKAAL_APPREF_BACKEND_URL", raising=False)
    updates = _orchestrator.hydrate_env_from_lock(graph, "frontend", lock_path=lock_path)
    assert updates == {"SKAAL_APPREF_BACKEND_URL": "https://backend.run.app"}
    assert os.environ["SKAAL_APPREF_BACKEND_URL"] == "https://backend.run.app"


def test_hydrate_env_raises_when_upstream_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    graph = _two_app_graph(tmp_path)
    # No project lock file written.
    with pytest.raises(RuntimeError, match="backend"):
        _orchestrator.hydrate_env_from_lock(graph, "frontend", lock_path=tmp_path / "missing.lock")


def test_local_endpoints_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "local-endpoints.json"
    _orchestrator.write_local_endpoints(
        {"backend": "http://127.0.0.1:8000", "frontend": "http://127.0.0.1:8050"},
        path=path,
    )
    out = _orchestrator.read_local_endpoints(path)
    assert out == {"backend": "http://127.0.0.1:8000", "frontend": "http://127.0.0.1:8050"}


def test_env_from_local_endpoints(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    graph = _two_app_graph(tmp_path)
    path = tmp_path / "local-endpoints.json"
    _orchestrator.write_local_endpoints({"backend": "http://127.0.0.1:8000"}, path=path)

    env = _orchestrator.env_from_local_endpoints(graph, "frontend", path=path)
    assert env == {"SKAAL_APPREF_BACKEND_URL": "http://127.0.0.1:8000"}


def test_select_app_url_prefers_apiUrl() -> None:
    assert (
        _orchestrator._select_app_url({"apiUrl": "http://a", "serviceUrl": "http://s"})
        == "http://a"
    )


def test_select_app_url_falls_back_to_service_url() -> None:
    assert _orchestrator._select_app_url({"serviceUrl": "http://s"}) == "http://s"


def test_select_app_url_picks_unique_url_key() -> None:
    assert _orchestrator._select_app_url({"frontendUrl": "http://f"}) == "http://f"


def test_select_app_url_returns_none_when_ambiguous() -> None:
    assert _orchestrator._select_app_url({"a": "x", "b": "y"}) is None
