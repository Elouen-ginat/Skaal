"""Smoke tests for `skaal deploy`.

These tests don't actually invoke Pulumi — they assert the verb wires up
the right pieces (parse → load → build → program callable) and surfaces a
clean `MissingExtraError` when the optional extras aren't installed.
"""

from __future__ import annotations

import sys
import textwrap
from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console
from typer.testing import CliRunner

from skaal import App, Store
from skaal.binding.model import BackendConfig, Environment, LockFile, Target
from skaal.cli.deploy_cmd import _gcp_required_services, _preflight_gcp_target, _print_stack_outputs
from skaal.cli.main import app as cli_app
from skaal.errors import SkaalDeployError

runner = CliRunner()


_FIXTURE = textwrap.dedent(
    """
    from skaal import App


    app = App("deploy-fixture")


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
    pkg_dir = tmp_path / "deploy_fixture_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    (pkg_dir / "app.py").write_text(_FIXTURE)
    (tmp_path / "skaal.toml").write_text(_SKAAL_TOML)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    sys.modules.pop("deploy_fixture_pkg", None)
    sys.modules.pop("deploy_fixture_pkg.app", None)
    return "deploy_fixture_pkg.app:app"


def test_deploy_fails_clean_when_pulumi_missing(
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
    result = runner.invoke(cli_app, ["deploy", fixture_app, "--env", "prod", "--yes"])
    assert result.exit_code != 0
    # The CLI's error boundary swallows the traceback; the error string
    # surfaces via the logger.
    assert "skaal[deploy,aws]" in (result.output or "") or "Pulumi" in (result.output or "")


def test_deploy_rejects_local_env(fixture_app: str) -> None:
    """`skaal deploy --env local` fails before reaching Pulumi."""
    result = runner.invoke(cli_app, ["deploy", fixture_app, "--env", "local", "--yes"])
    assert result.exit_code != 0


def test_print_stack_outputs_renders_values() -> None:
    buffer = StringIO()
    console = Console(file=buffer, force_terminal=False, color_system=None)

    _print_stack_outputs(
        {
            "public_url": type("OutputValue", (), {"value": "https://example.execute-api.aws"})(),
            "empty": type("OutputValue", (), {"value": None})(),
        },
        console,
    )

    rendered = buffer.getvalue()
    assert "Stack outputs:" in rendered
    assert "public_url = https://example.execute-api.aws" in rendered


def test_preflight_gcp_requires_project(monkeypatch: pytest.MonkeyPatch) -> None:
    app = App("deploy-fixture")

    @app.expose()
    async def greet(name: str) -> dict[str, str]:
        return {"hello": name}

    env = Environment(name="prod", target=Target.GCP, region="us-central1")
    bound = app.plan(env, lock=LockFile())
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GCP_PROJECT", raising=False)

    with pytest.raises(SkaalDeployError, match="project id"):
        _preflight_gcp_target(bound, env)


def test_preflight_gcp_requires_enabled_services(monkeypatch: pytest.MonkeyPatch) -> None:
    app = App("deploy-fixture")

    @app.storage
    class Sessions(Store[int]):
        pass

    @app.expose()
    async def greet(name: str) -> dict[str, str]:
        return {"hello": name}

    env = Environment(
        name="prod",
        target=Target.GCP,
        region="us-central1",
        backends={"gcp": BackendConfig(project="acme-prod")},
    )
    bound = app.plan(env, lock=LockFile())

    monkeypatch.setattr("skaal.cli.deploy_cmd._resolve_gcp_access_token", lambda: "token")
    monkeypatch.setattr(
        "skaal.cli.deploy_cmd._gcp_service_state",
        lambda project, service, token: (
            "DISABLED" if service == "firestore.googleapis.com" else "ENABLED"
        ),
    )

    with pytest.raises(SkaalDeployError, match=r"firestore\.googleapis\.com"):
        _preflight_gcp_target(bound, env)


def test_gcp_required_services_include_cloud_run_and_firestore() -> None:
    app = App("deploy-fixture")

    @app.storage
    class Sessions(Store[int]):
        pass

    @app.expose()
    async def greet(name: str) -> dict[str, str]:
        return {"hello": name}

    env = Environment(
        name="prod",
        target=Target.GCP,
        region="us-central1",
        backends={"gcp": BackendConfig(project="acme-prod")},
    )
    bound = app.plan(env, lock=LockFile())

    services = set(_gcp_required_services(bound))
    assert "run.googleapis.com" in services
    assert "artifactregistry.googleapis.com" in services
    assert "iam.googleapis.com" in services
    assert "firestore.googleapis.com" in services
