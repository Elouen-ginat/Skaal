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
from typing import Any

import pytest
from rich.console import Console
from typer.testing import CliRunner

from skaal import App, Store
from skaal.binding.model import BackendConfig, Environment, LockFile, Target
from skaal.cli.deploy_cmd import (
    _gcp_batch_enable_services,
    _gcp_disabled_services,
    _gcp_required_services,
    _preflight_gcp_target,
    _print_stack_outputs,
)
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


def _gcp_preflight_app() -> tuple[Any, Any]:
    """Shared fixture: an App with one Store + one function, bound on GCP."""
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
    return bound, env


def test_preflight_gcp_auto_enables_missing_services(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the active credentials carry `services.enable`, the preflight
    quietly enables what's missing and proceeds — no error raised."""
    bound, env = _gcp_preflight_app()

    monkeypatch.setattr("skaal.cli.deploy_cmd._gcp_service_usage_client", lambda: object())
    monkeypatch.setattr(
        "skaal.cli.deploy_cmd._gcp_disabled_services",
        lambda client, project, services: ("firestore.googleapis.com",),
    )
    monkeypatch.setattr(
        "skaal.cli.deploy_cmd._ensure_docker_artifact_registry_auth", lambda env: None
    )

    enable_calls: list[tuple[str, tuple[str, ...]]] = []

    def fake_enable(client: Any, project: str, services: Any, **_kwargs: Any) -> bool:
        enable_calls.append((project, tuple(services)))
        return True

    monkeypatch.setattr("skaal.cli.deploy_cmd._gcp_batch_enable_services", fake_enable)

    _preflight_gcp_target(bound, env)

    assert enable_calls == [("acme-prod", ("firestore.googleapis.com",))]


def test_preflight_gcp_falls_back_to_helpful_error_when_no_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When `serviceusage.services.enable` is denied, surface the
    `gcloud services enable …` recipe so the operator can self-serve."""
    bound, env = _gcp_preflight_app()

    monkeypatch.setattr("skaal.cli.deploy_cmd._gcp_service_usage_client", lambda: object())
    monkeypatch.setattr(
        "skaal.cli.deploy_cmd._gcp_disabled_services",
        lambda client, project, services: ("firestore.googleapis.com",),
    )
    monkeypatch.setattr(
        "skaal.cli.deploy_cmd._gcp_batch_enable_services",
        lambda *args, **kwargs: False,
    )

    with pytest.raises(SkaalDeployError, match=r"serviceUsageAdmin") as excinfo:
        _preflight_gcp_target(bound, env)
    assert "firestore.googleapis.com" in str(excinfo.value)


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
    expected_services = {
        "serviceusage.googleapis.com",
        "compute.googleapis.com",
        "run.googleapis.com",
        "artifactregistry.googleapis.com",
        "iam.googleapis.com",
        "firestore.googleapis.com",
    }
    assert services == expected_services


# ── `_gcp_disabled_services` + `_gcp_batch_enable_services` ────────────────────
#
# These exercise the helpers directly against a stub ServiceUsageClient. The
# stub mirrors the real client's keyword-only call signature
# (`get_service(name=…)`, `batch_enable_services(parent=…, service_ids=…)`)
# so the assertions also verify Skaal is calling the SDK correctly.

from google.api_core import exceptions as gax_exceptions  # noqa: E402
from google.cloud.service_usage_v1.types import State  # noqa: E402


class _StubService:
    """Stand-in for `google.cloud.service_usage_v1.types.Service`."""

    def __init__(self, state: State) -> None:
        self.state = state


class _StubOperation:
    """Stand-in for the long-running operation returned by `batch_enable_services`."""

    def __init__(self, *, raises: BaseException | None = None) -> None:
        self._raises = raises
        self.result_calls: list[float | None] = []

    def result(self, timeout: float | None = None) -> None:
        self.result_calls.append(timeout)
        if self._raises is not None:
            raise self._raises


class _StubServiceUsageClient:
    """Minimal `ServiceUsageClient` replacement for unit-test use."""

    def __init__(
        self,
        *,
        states: dict[str, State] | None = None,
        get_raises: dict[str, BaseException] | None = None,
        batch_operation: _StubOperation | None = None,
        batch_raises: BaseException | None = None,
    ) -> None:
        self._states = states or {}
        self._get_raises = get_raises or {}
        self._batch_operation = batch_operation
        self._batch_raises = batch_raises
        self.get_service_calls: list[str] = []
        self.batch_enable_calls: list[tuple[str, tuple[str, ...]]] = []

    def get_service(self, *, request: dict[str, Any]) -> _StubService:
        name = request["name"]
        self.get_service_calls.append(name)
        service = name.rsplit("/", 1)[-1]
        if service in self._get_raises:
            raise self._get_raises[service]
        return _StubService(state=self._states.get(service, State.ENABLED))

    def batch_enable_services(self, *, request: dict[str, Any]) -> _StubOperation:
        parent: str = request["parent"]
        service_ids: list[str] = request["service_ids"]
        self.batch_enable_calls.append((parent, tuple(service_ids)))
        if self._batch_raises is not None:
            raise self._batch_raises
        return self._batch_operation or _StubOperation()


def test_gcp_disabled_services_returns_only_the_disabled_ones() -> None:
    client = _StubServiceUsageClient(
        states={
            "run.googleapis.com": State.ENABLED,
            "firestore.googleapis.com": State.DISABLED,
        }
    )

    disabled = _gcp_disabled_services(
        client,
        "acme-prod",
        ("run.googleapis.com", "firestore.googleapis.com"),
    )

    assert disabled == ("firestore.googleapis.com",)
    assert client.get_service_calls == [
        "projects/acme-prod/services/run.googleapis.com",
        "projects/acme-prod/services/firestore.googleapis.com",
    ]


def test_gcp_disabled_services_treats_not_found_as_disabled() -> None:
    """`get_service` can 404 for APIs that were never enabled in the project."""
    client = _StubServiceUsageClient(
        get_raises={"firestore.googleapis.com": gax_exceptions.NotFound("missing")},
    )

    disabled = _gcp_disabled_services(client, "acme-prod", ("firestore.googleapis.com",))

    assert disabled == ("firestore.googleapis.com",)


def test_gcp_disabled_services_surfaces_serviceusage_bootstrap_failure() -> None:
    """If `serviceusage` itself is missing, surface the bootstrap message."""
    client = _StubServiceUsageClient(
        get_raises={
            "serviceusage.googleapis.com": gax_exceptions.NotFound("missing"),
        },
    )

    with pytest.raises(SkaalDeployError, match=r"serviceusage\.googleapis\.com"):
        _gcp_disabled_services(client, "acme-prod", ("serviceusage.googleapis.com",))


def test_gcp_disabled_services_surfaces_permission_denied() -> None:
    client = _StubServiceUsageClient(
        get_raises={"run.googleapis.com": gax_exceptions.PermissionDenied("denied")},
    )

    with pytest.raises(SkaalDeployError, match=r"serviceusage\.services\.get"):
        _gcp_disabled_services(client, "acme-prod", ("run.googleapis.com",))


def test_gcp_disabled_services_rejects_unknown_service_before_network() -> None:
    """Validation runs before any RPC, so an unknown identifier can't leak out."""
    client = _StubServiceUsageClient()

    with pytest.raises(SkaalDeployError, match="Unsupported GCP API identifier"):
        _gcp_disabled_services(client, "acme-prod", ("run.googleapis.com/../../evil",))

    assert client.get_service_calls == []


def test_gcp_batch_enable_services_succeeds() -> None:
    operation = _StubOperation()
    client = _StubServiceUsageClient(batch_operation=operation)

    assert (
        _gcp_batch_enable_services(client, "acme-prod", ("run.googleapis.com",), timeout_s=10.0)
        is True
    )
    assert client.batch_enable_calls == [("projects/acme-prod", ("run.googleapis.com",))]
    assert operation.result_calls == [10.0]


def test_gcp_batch_enable_services_returns_false_on_permission_denied() -> None:
    client = _StubServiceUsageClient(batch_raises=gax_exceptions.PermissionDenied("denied"))

    assert _gcp_batch_enable_services(client, "acme-prod", ("run.googleapis.com",)) is False


def test_gcp_batch_enable_services_raises_on_deadline_exceeded() -> None:
    """Timeouts surface a `SkaalDeployError` with the manual-enable recipe."""
    client = _StubServiceUsageClient(
        batch_operation=_StubOperation(raises=gax_exceptions.DeadlineExceeded("slow"))
    )

    with pytest.raises(SkaalDeployError, match="gcloud services enable"):
        _gcp_batch_enable_services(client, "acme-prod", ("run.googleapis.com",), timeout_s=1.0)


def test_gcp_batch_enable_services_raises_on_other_api_errors() -> None:
    client = _StubServiceUsageClient(
        batch_operation=_StubOperation(raises=gax_exceptions.InternalServerError("boom"))
    )

    with pytest.raises(SkaalDeployError, match="Could not enable GCP APIs"):
        _gcp_batch_enable_services(client, "acme-prod", ("run.googleapis.com",))


def test_gcp_batch_enable_services_validates_service_names() -> None:
    """Validation runs before any RPC, so an unknown identifier can't leak out."""
    client = _StubServiceUsageClient()

    with pytest.raises(SkaalDeployError, match="Unsupported GCP API identifier"):
        _gcp_batch_enable_services(client, "acme-prod", ("../../evil",))

    assert client.batch_enable_calls == []


def test_gcp_batch_enable_services_is_noop_on_empty_input() -> None:
    """Skipping the RPC when there's nothing to enable keeps deploys idempotent."""
    client = _StubServiceUsageClient()

    assert _gcp_batch_enable_services(client, "acme-prod", ()) is True
    assert client.batch_enable_calls == []
