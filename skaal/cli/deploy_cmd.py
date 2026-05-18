"""`skaal deploy` — render artefacts and drive Pulumi via the Automation API.

The verb walks `infer → bind`, renders the build tree via
`build_artefacts(...)`, then invokes `pulumi.automation` to spin up (or
update) a stack whose program is `pulumi_program_for(bound, env, build_dir)`.

On success the lock file is updated with the bindings the stack used so
follow-up runs of `skaal plan` short-circuit when nothing has changed.
The actual lock-write step is gated on whether the binder pinned any
new resources during this run.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import typer
from rich.console import Console

from skaal.binding._probe import detect_docker_daemon
from skaal.binding.model import Environment, LockEntry, LockFile, Plan, Target
from skaal.cli._errors import cli_error_boundary
from skaal.cli._load import (
    load_app,
    load_plan,
    resolve_app_spec,
    resolve_build_out_dir,
    resolve_lock_path,
)
from skaal.cli._params import Argument, Option
from skaal.cli._pulumi import apply_pulumi_defaults
from skaal.deploy import (
    PulumiProgram,
    build_artefacts,
    get_target,
    pulumi_program_for,
)
from skaal.deploy.gcp._project import resolve_gcp_project
from skaal.errors import MissingExtraError, SkaalDeployError
from skaal.inference.model import ResourceKind

app = typer.Typer(
    help="Provision infrastructure via Pulumi.",
    context_settings={"allow_interspersed_args": True},
)
log = logging.getLogger("skaal.cli")

_BASE_GCP_REQUIRED_SERVICES: tuple[str, ...] = (
    "serviceusage.googleapis.com",
    "compute.googleapis.com",
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "iam.googleapis.com",
)
_OPTIONAL_GCP_REQUIRED_SERVICES: frozenset[str] = frozenset(
    {
        "bigquery.googleapis.com",
        "cloudscheduler.googleapis.com",
        "cloudtasks.googleapis.com",
        "firestore.googleapis.com",
        "pubsub.googleapis.com",
        "secretmanager.googleapis.com",
        "sqladmin.googleapis.com",
        "storage.googleapis.com",
    }
)
_KNOWN_GCP_DEPLOY_SERVICES: frozenset[str] = frozenset(
    (*_BASE_GCP_REQUIRED_SERVICES, *_OPTIONAL_GCP_REQUIRED_SERVICES)
)


@app.callback(invoke_without_command=True)
@cli_error_boundary
def deploy(
    target: str | None = Argument(
        None,
        help=(
            "Dotted module:attribute pointing at an `App` instance. When omitted, "
            "falls back to `[tool.skaal].app` / `SKAAL_APP`."
        ),
    ),
    env_name: str | None = Option(
        None,
        "--env",
        "-e",
        help=(
            "Environment name from `skaal.toml`. When omitted, falls back to "
            "`[tool.skaal].default_environment` / `SKAAL_DEFAULT_ENVIRONMENT`, then `prod`."
        ),
    ),
    out_dir: Path | None = Option(
        None,
        "--out",
        "-o",
        help=(
            "Destination directory for rendered artefacts. Defaults to "
            "`[tool.skaal].out/<env>` or `./.skaal/build/<env>`."
        ),
    ),
    preview: bool = Option(
        False,
        "--preview",
        help="Run `pulumi preview` instead of `pulumi up`.",
    ),
    yes: bool = Option(
        False,
        "--yes",
        "-y",
        help="Skip the interactive confirmation prompt and apply immediately.",
    ),
    lock_path: Path | None = Option(
        None,
        "--lock",
        help="Path to `skaal.lock` (defaults to `[tool.skaal].lock` or `skaal.lock`).",
    ),
    dev: bool = Option(
        False,
        "--dev",
        help=(
            "Ship the local Skaal checkout inside each Lambda image instead of "
            "installing `skaal[...]` from PyPI. Use during the 0.4.0 alpha while "
            "the package is not yet published."
        ),
    ),
) -> None:
    app_spec = resolve_app_spec(target)
    skaal_app = load_app(app_spec)
    resolved_lock_path = resolve_lock_path(lock_path)
    loaded = load_plan(
        skaal_app,
        env_name,
        lock_path=resolved_lock_path,
        fallback_env="prod",
    )
    resolved_out_dir = resolve_build_out_dir(out_dir, loaded.env.name)

    written = build_artefacts(
        loaded.bound,
        loaded.env,
        app_spec,
        out_dir=resolved_out_dir,
        dev=dev,
    )
    console = Console()
    console.print(f"Rendered artefacts for [cyan]{loaded.env.name}[/cyan] → {written}")

    program = pulumi_program_for(loaded.bound, loaded.env, written)
    _run_pulumi(
        bound=loaded.bound,
        env=loaded.env,
        program=program,
        preview=preview,
        yes=yes,
        console=console,
    )

    _write_lock_pins(loaded.bound, loaded.env, lock_path=resolved_lock_path)
    console.print(f"[green]✓[/green] {'preview' if preview else 'deploy'} complete.")


def _run_pulumi(
    *,
    bound: Plan,
    env: Environment,
    program: PulumiProgram,
    preview: bool,
    yes: bool,
    console: Console,
) -> None:
    """Invoke the Pulumi Automation API against `program`.

    Imports `pulumi.automation` lazily so the rest of the CLI does not
    pay the import cost. Stack naming and stack-config wiring delegate
    to the registered `DeployTarget` so a new cloud target plugs in
    without editing this file.
    """
    apply_pulumi_defaults(console)
    _run_target_preflight(bound=bound, env=env)

    try:
        from pulumi import automation as auto
    except ImportError as exc:
        raise MissingExtraError(
            "`skaal deploy` requires the Pulumi SDKs. Install them with "
            "`pip install 'skaal[deploy,aws]'`."
        ) from exc

    # Importing the target package registers the target; the program
    # callable would do this on invocation, but we need the target
    # registered here too for stack-name / stack-config wiring.
    __import__(f"skaal.deploy.{env.target.value}")
    target = get_target(env.target)

    project_name = bound.app or "skaal"
    stack_name = target.stack_name(bound, env)
    console.print(f"Pulumi stack [bold]{stack_name}[/bold] (project=[cyan]{project_name}[/cyan])")

    stack = auto.create_or_select_stack(
        stack_name=stack_name,
        project_name=project_name,
        program=program,
    )
    for key, value in target.stack_config(env).items():
        stack.set_config(key, auto.ConfigValue(value=value))

    try:
        if preview:
            stack.preview(on_output=console.print)
        else:
            if not yes and not typer.confirm(
                f"Apply {stack_name!r} to target {env.target.value!r}?",
                default=False,
            ):
                raise typer.Abort()
            result = stack.up(on_output=console.print)
            _print_stack_outputs(result.outputs, console)
    except auto.CommandError as exc:  # pragma: no cover - network/integration path
        raise SkaalDeployError(f"Pulumi {('preview' if preview else 'up')} failed: {exc}") from exc


def _run_target_preflight(*, bound: Plan, env: Environment) -> None:
    """Run target-specific deploy preflight checks before invoking Pulumi."""
    if env.target is not Target.LOCAL:
        _preflight_docker()
    if env.target is Target.GCP:
        _preflight_gcp_target(bound, env)


def _preflight_docker() -> None:
    """Fail fast when the local Docker daemon is unavailable.

    Every cloud target (Cloud Run images, Lambda container images) builds
    via the local Docker daemon. Catching the missing daemon here gives a
    one-line error instead of a wall of Pulumi diagnostics.
    """
    state = detect_docker_daemon()
    if state == "running":
        return
    if state == "not-installed":
        raise SkaalDeployError(
            "Docker is required to build container images for cloud deploys, "
            "but the `docker` CLI is not on PATH. Install Docker Desktop "
            "(https://www.docker.com/products/docker-desktop) and try again."
        )
    raise SkaalDeployError(
        "Docker is installed but the daemon is not responding. Start Docker "
        "Desktop (or `systemctl start docker` on Linux) and try again."
    )


def _preflight_gcp_target(bound: Plan, env: Environment) -> None:
    """Fail fast when the active GCP project, ADC, or required APIs are missing."""
    project = resolve_gcp_project(env)
    if not project:
        raise SkaalDeployError(
            "GCP deploy requires a project id. Set `[env.<name>.backends.gcp].project` "
            "in `skaal.toml` or export `GOOGLE_CLOUD_PROJECT` / `GCP_PROJECT`."
        )

    token = _resolve_gcp_access_token()
    missing_services = [
        service
        for service in _gcp_required_services(bound)
        if _gcp_service_state(project, service, token) != "ENABLED"
    ]
    if missing_services:
        services = " ".join(missing_services)
        raise SkaalDeployError(
            f"GCP project {project!r} is missing required APIs for this deploy. "
            f"Enable them with:\n\n"
            f"  gcloud services enable {services} --project={project}\n"
        )

    _ensure_docker_artifact_registry_auth(env)


def _ensure_docker_artifact_registry_auth(env: Environment) -> None:
    """Configure Docker as a credential helper for Artifact Registry.

    Without this, ``docker push`` to ``<region>-docker.pkg.dev`` errors with
    ``denied: Unauthenticated request`` mid-deploy. ``gcloud auth
    configure-docker`` adds a credHelper entry to ``~/.docker/config.json``
    and is safe to re-run.

    Falls back to a clear error if ``gcloud`` is not on PATH.
    """
    import shutil
    import subprocess

    hostname = f"{env.region}-docker.pkg.dev" if env.region else "us-docker.pkg.dev"
    gcloud = shutil.which("gcloud")
    if gcloud is None:
        raise SkaalDeployError(
            "GCP deploy needs to push container images to Artifact Registry "
            "at "
            f"{hostname}, but the `gcloud` CLI is not on PATH. Install the "
            "Google Cloud SDK (https://cloud.google.com/sdk/docs/install) "
            "and re-run."
        )
    # ``shutil.which`` returns the full path including the Windows ``.cmd``
    # extension, which lets ``subprocess.run`` invoke it without ``shell=True``.
    try:
        subprocess.run(
            [gcloud, "auth", "configure-docker", hostname, "--quiet"],
            check=True,
            capture_output=True,
            timeout=30,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        stderr = getattr(exc, "stderr", b"")
        detail = stderr.decode("utf-8", errors="replace") if stderr else str(exc)
        raise SkaalDeployError(
            f"Could not configure Docker auth for {hostname}: {detail.strip()}"
        ) from exc


def _resolve_gcp_access_token() -> str:
    """Return an OAuth token suitable for Service Usage API checks."""
    explicit_token = os.getenv("GOOGLE_OAUTH_ACCESS_TOKEN")
    if explicit_token:
        return explicit_token

    try:
        import google.auth
        from google.auth.transport.requests import Request as GoogleAuthRequest
    except ImportError as exc:
        raise MissingExtraError(
            "`skaal deploy` for GCP requires the Google auth SDKs. Install them with "
            "`pip install 'skaal[deploy,gcp]'`."
        ) from exc

    try:
        # `google.auth.default` ships partial type stubs; pyright cannot
        # narrow the returned credentials object so we silence both
        # unknown-variable and unknown-member warnings here.
        credentials, _ = google.auth.default(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
    except Exception as exc:  # pragma: no cover - machine auth state
        raise SkaalDeployError(
            "GCP deploy requires Application Default Credentials. Run "
            "`gcloud auth application-default login` or set `GOOGLE_APPLICATION_CREDENTIALS`."
        ) from exc

    try:
        credentials.refresh(GoogleAuthRequest())  # pyright: ignore[reportUnknownMemberType]
    except Exception as exc:  # pragma: no cover - machine auth state
        raise SkaalDeployError(
            "GCP credentials were found but could not be refreshed. Re-run "
            "`gcloud auth application-default login` or fix the configured service account."
        ) from exc

    token = cast(
        str | None,
        credentials.token,  # pyright: ignore[reportUnknownMemberType]
    )
    if not token:
        raise SkaalDeployError(
            "GCP credentials were found but did not yield an access token for deploy preflight."
        )
    return token


def _gcp_required_services(bound: Plan) -> tuple[str, ...]:
    """Return the set of GCP APIs required by the current bound plan."""
    services: dict[str, None] = dict.fromkeys(_BASE_GCP_REQUIRED_SERVICES)

    for resource in bound.resources:
        if resource.external:
            continue

        kind = resource.inferred.kind
        if kind is ResourceKind.STORE:
            services["firestore.googleapis.com"] = None
        elif kind is ResourceKind.BLOB:
            services["storage.googleapis.com"] = None
        elif kind is ResourceKind.CHANNEL:
            services["pubsub.googleapis.com"] = None
        elif kind is ResourceKind.SECRET:
            services["secretmanager.googleapis.com"] = None
        elif kind is ResourceKind.SCHEDULE:
            services["cloudscheduler.googleapis.com"] = None
        elif kind is ResourceKind.JOB:
            services["cloudtasks.googleapis.com"] = None
        elif kind is ResourceKind.RELATIONAL:
            if resource.backend == "bigquery":
                services["bigquery.googleapis.com"] = None
            elif resource.backend == "postgres":
                services["sqladmin.googleapis.com"] = None
                services["secretmanager.googleapis.com"] = None

    return tuple(services)


def _validated_gcp_service_name(service: str) -> str:
    """Return `service` when it is one of Skaal's known deploy-time APIs."""
    if service in _KNOWN_GCP_DEPLOY_SERVICES:
        return service

    msg = (
        f"Unsupported GCP API identifier {service!r} encountered during deploy preflight. "
        "This is an internal Skaal bug."
    )
    raise SkaalDeployError(msg)


def _gcp_service_state(project: str, service: str, token: str) -> str | None:
    """Return the current Service Usage state for one API in `project`."""
    safe_service = _validated_gcp_service_name(service)
    safe_project = quote(project, safe="")
    request = Request(
        f"https://serviceusage.googleapis.com/v1/projects/{safe_project}/services/{quote(safe_service, safe='')}",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urlopen(request, timeout=10) as response:  # nosec B310 — fixed https://serviceusage.googleapis.com URL
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:  # pragma: no cover - network/integration path
        detail = exc.read().decode("utf-8", errors="replace")
        if safe_service == "serviceusage.googleapis.com":
            raise SkaalDeployError(
                f"GCP project {project!r} must have `serviceusage.googleapis.com` enabled "
                "before Skaal can verify the required deploy APIs."
            ) from exc
        raise SkaalDeployError(
            f"Could not verify whether GCP API {safe_service!r} is enabled for project {project!r}: "
            f"HTTP {exc.code}. {detail}"
        ) from exc
    except URLError as exc:  # pragma: no cover - network/integration path
        raise SkaalDeployError(
            f"Could not reach the GCP Service Usage API while checking project {project!r}."
        ) from exc

    state = payload.get("state")
    return state if isinstance(state, str) else None


def _print_stack_outputs(outputs: Mapping[str, Any] | None, console: Console) -> None:
    """Render exported stack outputs in a stable, Skaal-owned format."""
    if not outputs:
        return
    rendered: list[tuple[str, str]] = []
    for key in sorted(outputs):
        raw = outputs[key]
        value = getattr(raw, "value", raw)
        if value is None:
            continue
        rendered.append((key, str(value)))
    if not rendered:
        return

    console.print("Stack outputs:")
    for key, value in rendered:
        console.print(f"  [cyan]{key}[/cyan] = {value}")


def _write_lock_pins(bound: Plan, env: Environment, *, lock_path: Path) -> None:
    """Pin every non-external bound resource into `skaal.lock`.

    First-deploy runs convert the binder's defaults / overrides into
    explicit `LockEntry` rows so subsequent `skaal plan` runs short-circuit
    when nothing has changed. Already-locked entries are kept as-is.
    """
    existing = LockFile.load(lock_path)
    new_entries = dict(existing.entries)
    now = datetime.now(UTC)
    for resource in bound.resources:
        if resource.external:
            continue
        key = (env.name, resource.inferred.id)
        if key in new_entries:
            continue
        new_entries[key] = LockEntry(
            backend=resource.backend,
            region=resource.region,
            pinned_at=now,
            pinned_by="skaal-deploy",
            fingerprint=bound.bound_fingerprint or None,
        )

    if new_entries != existing.entries:
        updated = LockFile(version=existing.version, entries=new_entries)
        updated.save(lock_path)
