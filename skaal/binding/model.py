"""Pydantic models for the binding layer (ADR 028 §6.3, ADR 031 §3.3).

Every model in this module is a frozen pydantic `BaseModel` with
``extra="forbid"``. The set of fields is closed; unknown keys raise at
``model_validate`` time, mutation is a runtime error, and JSON round-trips
through ``model_dump_json(by_alias=True)``.

The eight types are:

- ``Target`` — the deployment platform (`local`, `aws`, `gcp`).
- ``BackendConfig`` — per-backend env config (project, dataset, emulator).
- ``EnvOverride`` — an entry in ``[env.<name>.overrides]``.
- ``Environment`` — one `skaal.toml` ``[env.<name>]`` block.
- ``LockEntry`` — one row of ``skaal.lock``.
- ``LockFile`` — the full pin-on-first-deploy state.
- ``PlannedResource`` — a `BlueprintResource` bound to one backend.
- ``Plan`` — the deterministic output of ``plan(blueprint, env, lock)``.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from skaal.inference.model import BlueprintResource, Edge


class Target(StrEnum):
    """The deployment platform an `Environment` targets (ADR 028 §6.3)."""

    LOCAL = "local"
    AWS = "aws"
    GCP = "gcp"


class BackendConfig(BaseModel):
    """Per-backend env config (project, dataset, emulator, region).

    The free-form ``options`` dict is validated against the backend's
    ``options_schema`` at bind time; until then the model is permissive so
    user-facing TOML loading does not reject keys the backend understands.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    region: str | None = None
    project: str | None = None
    dataset: str | None = None
    emulator: str | None = None
    table_prefix: str | None = None
    options: dict[str, Any] = {}


class EnvOverride(BaseModel):
    """An entry in ``[env.<name>.overrides]`` for a single un-pinned resource."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    backend: str
    region: str | None = None
    options: dict[str, str] = {}


class Environment(BaseModel):
    """One ``[env.<name>]`` block from `skaal.toml` (ADR 028 §6.3)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    target: Target
    region: str | None = None
    overrides: dict[str, EnvOverride] = {}
    backends: dict[str, BackendConfig] = {}

    @classmethod
    def load(cls, name: str = "local", *, path: Path | None = None) -> Environment:
        """Load one named environment from `skaal.toml`."""
        from skaal.binding.environment import load_environment

        return load_environment(name, path=path)

    @classmethod
    def load_all(cls, *, path: Path | None = None) -> dict[str, Environment]:
        """Load every environment from `skaal.toml`."""
        from skaal.binding.environment import load_environments

        return load_environments(path=path)


class LockEntry(BaseModel):
    """One pin in `skaal.lock`, keyed by `(env_name, resource_id)`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    backend: str
    region: str | None = None
    pinned_at: datetime
    pinned_by: str | None = None
    fingerprint: str | None = None


class LockFile(BaseModel):
    """The full pin-on-first-deploy state (ADR 028 §6.10).

    ``entries`` is keyed by ``(env_name, resource_id)``. The on-disk TOML
    form is the nested ``[entries.<env>."<resource_id>"]`` shape; the
    `skaal.binding.lock` module handles the conversion.
    """

    model_config = ConfigDict(extra="forbid")

    version: int = 1
    entries: dict[tuple[str, str], LockEntry] = {}

    @classmethod
    def load(cls, path: Path) -> LockFile:
        """Load `skaal.lock` from disk, or return an empty lock file."""
        from skaal.binding.lock import load_lock

        return load_lock(path)

    def save(self, path: Path) -> None:
        """Persist this lock file to disk."""
        from skaal.binding.lock import write_lock

        write_lock(path, self)


class PlannedResource(BaseModel):
    """An `InferredResource` bound to exactly one concrete backend.

    ``external`` is propagated from `ResourceOverrides.external` (set by
    `@app.external`). When ``True``, the deploy layer skips Pulumi
    provisioning for this resource and the runtime adapter reads the
    connection from `Environment.backends[external_name]` instead.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    inferred: BlueprintResource
    backend: str
    region: str | None = None
    options: dict[str, str] = {}
    backend_config: BackendConfig | None = None
    pinned: bool
    external: bool = False
    external_name: str | None = None


class Plan(BaseModel):
    """The deterministic output of ``bind(plan, env, lock)``.

    ``app_fingerprint`` mirrors ``InferredPlan.fingerprint`` through the
    bind step. ``bound_fingerprint`` is the SHA-256 (first 16 hex chars)
    of the canonical-serialised resources + edges + environment name; it
    is what the deploy layer tags every cloud resource with so a
    follow-up `skaal plan` can short-circuit when nothing has changed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    app: str
    environment: str
    resources: tuple[PlannedResource, ...] = ()
    edges: tuple[Edge, ...] = ()
    app_fingerprint: str = ""
    bound_fingerprint: str = ""
