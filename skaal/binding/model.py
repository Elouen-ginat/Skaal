"""Pydantic models for the binding layer (ADR 028 §6.3, ADR 031 §3.3).

Every model in this module is a frozen pydantic `BaseModel` with
``extra="forbid"``. The set of fields is closed; unknown keys raise at
``model_validate`` time, mutation is a runtime error, and JSON round-trips
through ``model_dump_json(by_alias=True)``.

The eight types are:

- ``Target`` — the deployment platform (`local`, `aws`, `gcp`).
- ``BackendConfig`` — per-backend env config (project, dataset, emulator).
- ``ResourceOverride`` — an entry in ``[env.<name>.overrides]``.
- ``Environment`` — one `skaal.toml` ``[env.<name>]`` block.
- ``LockEntry`` — one row of ``skaal.lock``.
- ``LockFile`` — the full pin-on-first-deploy state.
- ``BoundResource`` — an `InferredResource` bound to one backend.
- ``BoundPlan`` — the deterministic output of ``bind(plan, env, lock)``.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict

from skaal.inference.model import Edge, InferredResource


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


class ResourceOverride(BaseModel):
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
    overrides: dict[str, ResourceOverride] = {}
    backends: dict[str, BackendConfig] = {}


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


class BoundResource(BaseModel):
    """An `InferredResource` bound to exactly one concrete backend."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    inferred: InferredResource
    backend: str
    region: str | None = None
    options: dict[str, str] = {}
    backend_config: BackendConfig | None = None
    pinned: bool


class BoundPlan(BaseModel):
    """The deterministic output of ``bind(plan, env, lock)``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    app: str
    environment: str
    resources: tuple[BoundResource, ...] = ()
    edges: tuple[Edge, ...] = ()
