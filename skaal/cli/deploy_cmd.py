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

import logging
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from google.cloud import service_usage_v1

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
    """Fail fast when the active GCP project or ADC are missing.

    Required APIs that are not yet enabled are enabled automatically via
    ``serviceusage.services.batchEnable`` when the active credentials carry
    ``serviceusage.services.enable`` (commonly through
    ``roles/serviceusage.serviceUsageAdmin``). Credentials without that
    permission fall back to a clear error pointing the user at the
    matching ``gcloud services enable`` command.
    """
    project = resolve_gcp_project(env)
    if not project:
        raise SkaalDeployError(
            "GCP deploy requires a project id. Set `[env.<name>.backends.gcp].project` "
            "in `skaal.toml` or export `GOOGLE_CLOUD_PROJECT` / `GCP_PROJECT`."
        )

    client = _gcp_service_usage_client()
    required = _gcp_required_services(bound)
    missing_services = _gcp_disabled_services(client, project, required)
    if missing_services:
        console = Console()
        console.print(
            f"[dim]Enabling missing GCP APIs on {project}: {', '.join(missing_services)}…[/dim]"
        )
        enabled = _gcp_batch_enable_services(client, project, missing_services)
        if not enabled:
            services = " ".join(missing_services)
            raise SkaalDeployError(
                f"GCP project {project!r} is missing required APIs for this deploy and "
                "the active credentials lack `serviceusage.services.enable`. Grant "
                "`roles/serviceusage.serviceUsageAdmin` on the deploy identity and "
                "retry, or enable the APIs manually with:\n\n"
                f"  gcloud services enable {services} --project={project}\n"
            )
        console.print(f"[green]✓[/green] enabled {len(missing_services)} GCP API(s).")

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


def _gcp_service_usage_client() -> service_usage_v1.ServiceUsageClient:
    """Return a configured Service Usage client.

    Authentication uses Application Default Credentials (`gcloud auth
    application-default login`, `GOOGLE_APPLICATION_CREDENTIALS`, or the
    runtime-mounted credentials inside a GCE / Cloud Run / Workload-Identity
    environment). The client handles token refresh and retries internally;
    Skaal no longer hand-rolls OAuth bearer-token math against
    `serviceusage.googleapis.com`.
    """
    try:
        from google.cloud import service_usage_v1
    except ImportError as exc:
        raise MissingExtraError(
            "`skaal deploy` for GCP requires the Google Cloud SDKs. Install them with "
            "`pip install 'skaal[deploy,gcp]'`."
        ) from exc

    try:
        return service_usage_v1.ServiceUsageClient()
    except Exception as exc:  # pragma: no cover - machine auth state
        raise SkaalDeployError(
            "GCP deploy requires Application Default Credentials. Run "
            "`gcloud auth application-default login` or set `GOOGLE_APPLICATION_CREDENTIALS`."
        ) from exc


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


def _gcp_disabled_services(
    client: service_usage_v1.ServiceUsageClient,
    project: str,
    services: Sequence[str],
) -> tuple[str, ...]:
    """Return the subset of `services` that are not yet enabled on `project`.

    Raises ``SkaalDeployError`` for any condition other than "this single
    service is disabled" — in particular when ``serviceusage.googleapis.com``
    itself is not yet enabled (chicken-and-egg case the caller can't fix
    automatically) or when the deploy identity cannot read service state.
    """
    from google.api_core import exceptions as gax_exceptions
    from google.cloud.service_usage_v1.types import State

    disabled: list[str] = []
    for service in services:
        safe = _validated_gcp_service_name(service)
        name = f"projects/{project}/services/{safe}"
        try:
            # `google-cloud-service-usage`'s pyright stubs report unknown
            # members for the GAPIC overloads; the runtime call is correct.
            svc = client.get_service(request={"name": name})  # pyright: ignore[reportUnknownMemberType]
        except gax_exceptions.PermissionDenied as exc:
            raise SkaalDeployError(
                f"Cannot read the state of GCP API {safe!r} on project {project!r}: "
                "the deploy identity lacks `serviceusage.services.get`. Grant "
                "`roles/serviceusage.serviceUsageViewer` (or admin) and retry."
            ) from exc
        except gax_exceptions.NotFound as exc:
            if safe == "serviceusage.googleapis.com":
                raise SkaalDeployError(
                    f"GCP project {project!r} must have `serviceusage.googleapis.com` enabled "
                    "before Skaal can verify the required deploy APIs."
                ) from exc
            disabled.append(safe)
            continue
        except gax_exceptions.GoogleAPICallError as exc:
            raise SkaalDeployError(
                f"Could not verify whether GCP API {safe!r} is enabled for project {project!r}: "
                f"{exc}"
            ) from exc

        if svc.state != State.ENABLED:
            disabled.append(safe)
    return tuple(disabled)


def _gcp_batch_enable_services(
    client: service_usage_v1.ServiceUsageClient,
    project: str,
    services: Sequence[str],
    *,
    timeout_s: float = 180.0,
) -> bool:
    """Enable `services` on `project` via Service Usage `batchEnable`.

    Returns ``True`` when the long-running operation completes successfully,
    ``False`` when the active credentials lack
    ``serviceusage.services.enable`` (caller falls back to the manual-enable
    recipe). Any other API failure raises ``SkaalDeployError``.
    """
    if not services:
        return True
    safe_services = [_validated_gcp_service_name(s) for s in services]

    from google.api_core import exceptions as gax_exceptions

    try:
        # `google-cloud-service-usage`'s pyright stubs report unknown members
        # on both the GAPIC overloads and the returned LRO; the runtime
        # call shape matches the documented one (`request=` dict, then
        # `Operation.result(timeout=…)`).
        operation = client.batch_enable_services(  # pyright: ignore[reportUnknownMemberType]
            request={
                "parent": f"projects/{project}",
                "service_ids": safe_services,
            }
        )
        operation.result(timeout=timeout_s)  # pyright: ignore[reportUnknownMemberType]
    except gax_exceptions.PermissionDenied:
        return False
    except gax_exceptions.DeadlineExceeded as exc:
        raise SkaalDeployError(
            f"Timed out after {timeout_s:.0f}s waiting for GCP APIs to enable on project "
            f"{project!r}. Re-run the deploy, or enable them manually with "
            f"`gcloud services enable {' '.join(safe_services)} --project={project}`."
        ) from exc
    except gax_exceptions.GoogleAPICallError as exc:
        raise SkaalDeployError(f"Could not enable GCP APIs on project {project!r}: {exc}") from exc
    return True


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
