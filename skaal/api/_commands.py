"""Typed wrappers for the landed CLI commands."""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TYPE_CHECKING, Never, TypeAlias

from rich.console import Console

from skaal.app import App
from skaal.binding import load_lock
from skaal.binding.model import Environment, LockFile
from skaal.cli._load import AppSpec, load_app, load_bound_plan, load_plan
from skaal.cli.deploy_cmd import _run_pulumi, _write_lock_pins
from skaal.deploy import BuildManifest, build_artefacts, pulumi_program_for
from skaal.stubs import StubManifest, discover_app, emit_stubs

if TYPE_CHECKING:
    from skaal.binding.model import BoundPlan

StubSource: TypeAlias = str | Path


@dataclass(frozen=True)
class BuildResult:
    """Result of `skaal.api.build`."""

    app_spec: AppSpec
    bound: BoundPlan
    env: Environment
    build_dir: Path
    manifest: BuildManifest


@dataclass(frozen=True)
class DeployResult:
    """Result of `skaal.api.deploy`."""

    build: BuildResult
    preview: bool
    lock_updated: bool
    lock: LockFile


@dataclass(frozen=True)
class DoctorReport:
    """Environment report returned by `skaal.api.doctor`."""

    python_version: str
    pulumi_path: str | None
    skaal_version: str


@dataclass(frozen=True)
class StubEmitResult:
    """Result of `skaal.api.stubs`."""

    app_name: str
    package_name: str
    out_dir: Path
    manifest: StubManifest


def init() -> Never:
    """Raise the same not-yet-implemented error as `skaal init`.

    Raises:
        NotImplementedError: Always, until the project scaffolder lands.
    """
    raise NotImplementedError(
        "`skaal init` is not yet implemented in 0.4.0-alpha. "
        "The project scaffolder is rewritten in Phase 5 of ADR 028."
    )


def doctor() -> DoctorReport:
    """Return the local Skaal toolchain status.

    Returns:
        The Python version, Pulumi location, and installed Skaal version.

    Raises:
        RuntimeError: If the Skaal package cannot be imported.
    """
    try:
        skaal_version = version("skaal")
    except PackageNotFoundError as exc:  # pragma: no cover - packaging edge case
        raise RuntimeError("Skaal package metadata is not available.") from exc

    return DoctorReport(
        python_version=sys.version.split()[0],
        pulumi_path=shutil.which("pulumi"),
        skaal_version=skaal_version,
    )


def build(
    target: App | str,
    *,
    env_name: str = "local",
    toml_path: Path = Path("skaal.toml"),
    lock_path: Path = Path("skaal.lock"),
    out_dir: Path | None = None,
    python_version: str = "3.11",
) -> BuildResult:
    """Render deploy artefacts from a bound plan.

    Args:
        target: `module:attribute` reference or live `App` instance.
        env_name: Environment name from `skaal.toml`.
        toml_path: Settings file path.
        lock_path: Lock file path used during binding.
        out_dir: Optional destination directory for rendered artefacts.
        python_version: Python minor version embedded in rendered artefacts.

    Returns:
        The bound plan, environment, output directory, and parsed manifest.
    """
    app_spec, skaal_app = _resolve_build_target(target)
    loaded = load_plan(skaal_app, env_name, toml_path=toml_path, lock_path=lock_path)
    build_dir = build_artefacts(
        loaded.bound,
        loaded.env,
        app_spec,
        out_dir=out_dir,
        python_version=python_version,
    )
    return BuildResult(
        app_spec=app_spec,
        bound=loaded.bound,
        env=loaded.env,
        build_dir=build_dir,
        manifest=_load_build_manifest(build_dir),
    )


def deploy(
    target: App | str,
    *,
    env_name: str = "prod",
    toml_path: Path = Path("skaal.toml"),
    lock_path: Path = Path("skaal.lock"),
    out_dir: Path | None = None,
    preview: bool = False,
    yes: bool = False,
) -> DeployResult:
    """Render artefacts, invoke Pulumi, and update `skaal.lock`.

    Args:
        target: `module:attribute` reference or live `App` instance.
        env_name: Environment name from `skaal.toml`.
        toml_path: Settings file path.
        lock_path: Lock file path (created on first deploy).
        out_dir: Optional destination directory for rendered artefacts.
        preview: When true, run `pulumi preview` instead of `pulumi up`.
        yes: When true, skip the interactive confirmation prompt.

    Returns:
        The build result plus the updated lock snapshot.
    """
    build_result = build(
        target,
        env_name=env_name,
        toml_path=toml_path,
        lock_path=lock_path,
        out_dir=out_dir,
    )
    existing_lock = load_lock(lock_path)
    program = pulumi_program_for(build_result.bound, build_result.env, build_result.build_dir)
    _run_pulumi(
        bound=build_result.bound,
        env=build_result.env,
        program=program,
        preview=preview,
        yes=yes,
        console=Console(),
    )
    _write_lock_pins(build_result.bound, build_result.env, lock_path=lock_path)
    updated_lock = load_lock(lock_path)
    return DeployResult(
        build=build_result,
        preview=preview,
        lock_updated=updated_lock.entries != existing_lock.entries,
        lock=updated_lock,
    )


def run(
    target: App | str,
    *,
    env_name: str = "local",
    toml_path: Path = Path("skaal.toml"),
    lock_path: Path = Path("skaal.lock"),
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    """Run a Skaal app locally.

    Args:
        target: `module:attribute` reference or live `App` instance.
        env_name: Environment name from `skaal.toml`.
        toml_path: Settings file path.
        lock_path: Lock file path used during binding.
        host: Bind host.
        port: Bind port.
    """
    skaal_app = _resolve_app_target(target)
    bound = load_bound_plan(skaal_app, env_name, toml_path=toml_path, lock_path=lock_path)

    from skaal.runtime import LocalRuntime

    LocalRuntime.from_bound_plan(bound, skaal_app).serve(host=host, port=port)


def stubs(
    source: StubSource,
    out_dir: Path,
    *,
    package_name: str | None = None,
) -> StubEmitResult:
    """Emit a typed `.pyi` package describing a Skaal app.

    Args:
        source: Path to a Skaal app package, or a `module:attribute` reference.
        out_dir: Destination directory for the emitted stub package.
        package_name: Optional Python package name consumers will import.

    Returns:
        The output directory, package name, app name, and parsed stub manifest.
    """
    skaal_app = discover_app(source)
    package = package_name or out_dir.resolve().name
    written = emit_stubs(app=skaal_app, out_dir=out_dir, package_name=package)
    manifest_path = written / "_manifest.json"
    manifest = StubManifest.from_json(manifest_path.read_text(encoding="utf-8"))
    return StubEmitResult(
        app_name=skaal_app.name,
        package_name=package,
        out_dir=written,
        manifest=manifest,
    )


def _resolve_build_target(target: App | str) -> tuple[AppSpec, App]:
    """Resolve a CLI/API target into both `AppSpec` and `App`."""
    if isinstance(target, str):
        app_spec = AppSpec.parse(target)
        resolved = load_app(app_spec)
        if not isinstance(resolved, App):
            msg = f"`{target}` did not resolve to a Skaal `App` instance."
            raise TypeError(msg)
        return app_spec, resolved
    return AppSpec.for_app(target), target


def _resolve_app_target(target: App | str) -> App:
    """Resolve a CLI/API target into a live `App`."""
    if isinstance(target, str):
        resolved = load_app(target)
        if not isinstance(resolved, App):
            msg = f"`{target}` did not resolve to a Skaal `App` instance."
            raise TypeError(msg)
        return resolved
    return target


def _load_build_manifest(build_dir: Path) -> BuildManifest:
    """Read the rendered `manifest.json` next to a build."""
    manifest_path = build_dir / "manifest.json"
    return BuildManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
