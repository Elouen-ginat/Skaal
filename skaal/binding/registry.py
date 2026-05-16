"""Backend registry (ADR 028 §6.12, ADR 031 §3.4).

A single tuple — `REGISTRY` — lists every backend Skaal knows about. Each
entry pairs a typed `Backend` token with its operational metadata
(targets, capabilities, options schema). The binder, the import-time
validation, the user-facing `skaal backends list`, and the typed
`.native()` escape all read from this one tuple.

The registry is a static module: adding a new backend is one PR (subclass,
entry, test). There is no entry-point discovery and no TOML catalog
overlay; third-party backends re-enter through a separate
``BackendProtocol`` work item in a later release.
"""

from __future__ import annotations

from collections.abc import Iterable
from threading import Lock
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from skaal.backends._base import Backend
from skaal.backends._tokens import (
    ALL_TOKENS,
    S3,
    ApigwLambda,
    Apscheduler,
    Asyncio,
    AwsSecretsManager,
    CloudRun,
    CloudSchedulerCloudRun,
    CloudTasksCloudRun,
    DotenvSecret,
    DynamoDB,
    EventBridgeLambda,
    FilesystemBlob,
    Firestore,
    GcpSecretManager,
    Gcs,
    InProcessChannel,
    Lambda,
    Postgres,
    Pubsub,
    Redis,
    RedisChannel,
    Sqlite,
    Sqs,
    SqsLambdaWorker,
    Uvicorn,
)
from skaal.binding.model import Target
from skaal.inference.model import ResourceKind


class BackendCapabilities(BaseModel):
    """Optional feature flags a backend may declare (ADR 028 §6.12)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ttl: bool = False
    secondary_indexes: bool = False
    transactions: bool = False
    streaming: bool = False
    row_updates: bool = False
    partitioning: bool = False


class BackendOptions(BaseModel):
    """Permissive base options schema (Phase 3).

    Backend-specific option schemas inherit from this and tighten the
    fields they care about; Phase 4 narrows each backend's schema as the
    deploy templates need the fields. Phase 3 keeps the door open so user
    TOML overrides do not fail before the registry has a chance to look at
    them.
    """

    model_config = ConfigDict(extra="allow")


class BackendDefault(BaseModel):
    """One `(ResourceKind, Target)` slot for which a backend is the default."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: ResourceKind
    target: Target


class BackendEntry(BaseModel):
    """One row of the registry (ADR 028 §6.12)."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    # Pydantic's schema generator rejects already-parametrised generics in
    # `type[...]` fields, so we keep the bare `Backend` here. The runtime
    # check `isinstance(token, type) and issubclass(token, Backend)` is
    # the contract; the `token_class` property below exposes a fully-typed
    # `type[Backend[Any]]` for static-typing consumers.
    token: type[Backend]  # pyright: ignore[reportMissingTypeArgument]
    targets: frozenset[Target]
    capabilities: BackendCapabilities = BackendCapabilities()
    options_schema: type[BaseModel] = BackendOptions
    default_for: frozenset[BackendDefault] = Field(default_factory=frozenset)

    @property
    def token_class(self) -> type[Backend[Any]]:
        """Return ``token`` typed as a fully-parametrised `Backend[Any]`.

        Pyright reports `type[Backend]` (the field's storage type) as
        partially unknown because `Backend` has an unbound `NativeClientT`.
        Consumers that read identity / kinds / name should go through
        ``token_class`` to retain strict-typing cleanliness; the runtime
        value is identical to ``token``.
        """
        return self.token  # type: ignore[return-value]

    @property
    def name(self) -> str:
        """Return the canonical backend name."""
        return self.token_class.name

    @property
    def kinds(self) -> frozenset[ResourceKind]:
        """Return the `ResourceKind`s this backend can host."""
        return frozenset(ResourceKind(kind) for kind in self.token_class.kinds)

    def supports_kind(self, kind: ResourceKind | str) -> bool:
        """Return whether this backend can host `kind`."""
        if isinstance(kind, ResourceKind):
            return kind in self.kinds
        return kind in self.token_class.kinds

    def is_default_for(self, kind: ResourceKind, target: Target) -> bool:
        """Return whether this entry is the binder default for `(kind, target)`."""
        return BackendDefault(kind=kind, target=target) in self.default_for


def _entry(
    token: type[Backend[Any]],
    targets: frozenset[Target],
    *,
    capabilities: BackendCapabilities | None = None,
    default_for: frozenset[BackendDefault] | None = None,
) -> BackendEntry:
    return BackendEntry(
        token=token,
        targets=targets,
        capabilities=capabilities or BackendCapabilities(),
        options_schema=BackendOptions,
        default_for=default_for or frozenset(),
    )


def _default_cells(
    token: type[Backend[Any]],
    *targets: Target,
    kinds: Iterable[ResourceKind] | None = None,
) -> frozenset[BackendDefault]:
    default_kinds = tuple(kinds) if kinds is not None else (ResourceKind(kind) for kind in token.kinds)
    return frozenset(
        BackendDefault(kind=kind, target=target) for kind in default_kinds for target in targets
    )


_LOCAL = frozenset({Target.LOCAL})
_AWS = frozenset({Target.AWS})
_GCP = frozenset({Target.GCP})
_ALL_TARGETS = frozenset({Target.LOCAL, Target.AWS, Target.GCP})


REGISTRY: tuple[BackendEntry, ...] = (
    _entry(
        Sqlite,
        _LOCAL,
        capabilities=BackendCapabilities(transactions=True, secondary_indexes=True),
        default_for=_default_cells(Sqlite, Target.LOCAL),
    ),
    _entry(
        Postgres,
        _ALL_TARGETS,
        capabilities=BackendCapabilities(
            transactions=True, row_updates=True, secondary_indexes=True
        ),
        default_for=_default_cells(Postgres, Target.AWS, Target.GCP),
    ),
    _entry(
        Redis,
        _ALL_TARGETS,
        capabilities=BackendCapabilities(ttl=True, streaming=True),
    ),
    _entry(
        DynamoDB,
        _AWS,
        capabilities=BackendCapabilities(ttl=True, secondary_indexes=True),
        default_for=_default_cells(DynamoDB, Target.AWS),
    ),
    _entry(
        Firestore,
        _GCP,
        capabilities=BackendCapabilities(secondary_indexes=True),
        default_for=_default_cells(Firestore, Target.GCP),
    ),
    _entry(S3, _AWS, default_for=_default_cells(S3, Target.AWS)),
    _entry(Gcs, _GCP, default_for=_default_cells(Gcs, Target.GCP)),
    _entry(FilesystemBlob, _LOCAL, default_for=_default_cells(FilesystemBlob, Target.LOCAL)),
    _entry(
        InProcessChannel,
        _LOCAL,
        capabilities=BackendCapabilities(streaming=True),
        default_for=_default_cells(InProcessChannel, Target.LOCAL),
    ),
    _entry(RedisChannel, _ALL_TARGETS, capabilities=BackendCapabilities(streaming=True)),
    _entry(
        Sqs,
        _AWS,
        capabilities=BackendCapabilities(streaming=True),
        default_for=_default_cells(Sqs, Target.AWS),
    ),
    _entry(
        Pubsub,
        _GCP,
        capabilities=BackendCapabilities(streaming=True),
        default_for=_default_cells(Pubsub, Target.GCP),
    ),
    _entry(Asyncio, _LOCAL, default_for=_default_cells(Asyncio, Target.LOCAL)),
    _entry(Lambda, _AWS, default_for=_default_cells(Lambda, Target.AWS)),
    _entry(CloudRun, _GCP, default_for=_default_cells(CloudRun, Target.GCP)),
    _entry(Uvicorn, _LOCAL, default_for=_default_cells(Uvicorn, Target.LOCAL)),
    _entry(ApigwLambda, _AWS, default_for=_default_cells(ApigwLambda, Target.AWS)),
    _entry(Apscheduler, _LOCAL, default_for=_default_cells(Apscheduler, Target.LOCAL)),
    _entry(
        EventBridgeLambda,
        _AWS,
        default_for=_default_cells(EventBridgeLambda, Target.AWS),
    ),
    _entry(
        CloudSchedulerCloudRun,
        _GCP,
        default_for=_default_cells(CloudSchedulerCloudRun, Target.GCP),
    ),
    _entry(SqsLambdaWorker, _AWS, default_for=_default_cells(SqsLambdaWorker, Target.AWS)),
    _entry(
        CloudTasksCloudRun,
        _GCP,
        default_for=_default_cells(CloudTasksCloudRun, Target.GCP),
    ),
    _entry(DotenvSecret, _LOCAL, default_for=_default_cells(DotenvSecret, Target.LOCAL)),
    _entry(
        AwsSecretsManager,
        _AWS,
        default_for=_default_cells(AwsSecretsManager, Target.AWS),
    ),
    _entry(
        GcpSecretManager,
        _GCP,
        default_for=_default_cells(GcpSecretManager, Target.GCP),
    ),
)


# Mutable storage for plugin-contributed entries. `REGISTRY` above is the
# in-tree baseline; `_EXTRA` holds anything added at runtime via
# `register_backend(...)` (typically by `skaal.plugins`). The two are
# stitched together on every lookup so the in-tree consistency invariant
# stays loud while still allowing external libs to add backends.
_LOCK: Lock = Lock()
_EXTRA: list[BackendEntry] = []
_EXTRA_BY_NAME: dict[str, BackendEntry] = {}
_EXTRA_BY_TOKEN: dict[type[Backend[Any]], BackendEntry] = {}


_BY_NAME: dict[str, BackendEntry] = {entry.token_class.name: entry for entry in REGISTRY}
_BY_TOKEN: dict[type[Backend[Any]], BackendEntry] = {entry.token_class: entry for entry in REGISTRY}


def all_entries() -> tuple[BackendEntry, ...]:
    """Return every registered entry — built-in plus plugin-contributed."""
    _ensure_plugins_loaded()
    with _LOCK:
        return REGISTRY + tuple(_EXTRA)


def register_backend(entry: BackendEntry) -> None:
    """Register a new `BackendEntry` (typically from a `SkaalPlugin`).

    Re-registering an already-known backend token is a silent no-op so
    plugin idempotency does not crash a deploy. Conflicting registrations
    (same `token.name` but different token classes) raise.

    Raises:
        SkaalConfigError: If a different token already owns this name.
    """
    token = entry.token_class
    name = token.name
    with _LOCK:
        existing_builtin = _BY_NAME.get(name)
        existing_extra = _EXTRA_BY_NAME.get(name)
        existing = existing_builtin or existing_extra
        if existing is not None:
            if existing.token_class is token:
                return
            from skaal.errors import SkaalConfigError

            raise SkaalConfigError(
                f"Backend name {name!r} is already registered to "
                f"{existing.token_class.__name__!r}; cannot re-register to "
                f"{token.__name__!r}."
            )
        _EXTRA.append(entry)
        _EXTRA_BY_NAME[name] = entry
        _EXTRA_BY_TOKEN[token] = entry


def lookup(name: str) -> BackendEntry:
    """Return the registry entry whose ``token.name`` matches.

    Raises:
        UnknownBackendError: if no entry matches.
    """
    _ensure_plugins_loaded()
    with _LOCK:
        entry = _BY_NAME.get(name) or _EXTRA_BY_NAME.get(name)
        if entry is not None:
            return entry
        valid = tuple(sorted({*_BY_NAME, *_EXTRA_BY_NAME}))
    from skaal.errors import UnknownBackendError

    raise UnknownBackendError(name, valid)


def lookup_token(token: type[Backend[Any]]) -> BackendEntry:
    """Return the registry entry for a `Backend` subclass identity."""
    _ensure_plugins_loaded()
    with _LOCK:
        entry = _BY_TOKEN.get(token) or _EXTRA_BY_TOKEN.get(token)
        if entry is not None:
            return entry
        valid = tuple(sorted({*_BY_NAME, *_EXTRA_BY_NAME}))
    from skaal.errors import UnknownBackendError

    raise UnknownBackendError(token.name, valid)


def default_entry_for(kind: ResourceKind, target: Target) -> BackendEntry:
    """Return the built-in default backend entry for `(kind, target)`."""
    for entry in REGISTRY:
        if entry.is_default_for(kind, target):
            return entry
    msg = f"no default backend registered for kind={kind.value!r} target={target.value!r}"
    raise RuntimeError(msg)


def tokens_for(kind: str, target: Target) -> tuple[BackendEntry, ...]:
    """Return every registered entry that can host ``kind`` on ``target``."""
    _ensure_plugins_loaded()
    with _LOCK:
        merged = REGISTRY + tuple(_EXTRA)
    return tuple(
        entry for entry in merged if target in entry.targets and kind in entry.token_class.kinds
    )


def _ensure_plugins_loaded() -> None:
    """Trigger lazy plugin discovery on first lookup.

    The import lives inside the function body to avoid a circular import
    between `skaal.plugins` and `skaal.binding.registry`: `skaal.plugins`
    calls `register_backend` (defined here), and this module triggers
    `load_plugins()` from there. Module-level imports would form a cycle
    at package load.
    """
    from skaal.plugins import load_plugins

    load_plugins()


def _reset_for_tests() -> None:
    """Clear plugin-contributed entries (test-only helper)."""
    with _LOCK:
        _EXTRA.clear()
        _EXTRA_BY_NAME.clear()
        _EXTRA_BY_TOKEN.clear()


def _registry_consistency_check() -> None:
    """Assert at import time that every token is registered exactly once."""
    seen: set[type[Backend[Any]]] = set()
    default_cells: set[BackendDefault] = set()
    for entry in REGISTRY:
        token = entry.token_class
        if token in seen:
            msg = f"backend token {token.__name__} registered twice"
            raise RuntimeError(msg)
        seen.add(token)
        for default in entry.default_for:
            cell_repr = f"({default.kind.value}, {default.target.value})"
            if default.target not in entry.targets:
                msg = (
                    f"default cell {cell_repr} points to "
                    f"{token.__name__}, but that backend does not target {default.target.value!r}"
                )
                raise RuntimeError(msg)
            if not entry.supports_kind(default.kind):
                msg = (
                    f"default cell {cell_repr} points to "
                    f"{token.__name__}, but that backend does not host {default.kind.value!r}"
                )
                raise RuntimeError(msg)
            if default in default_cells:
                msg = (
                    f"default cell ({default.kind.value}, {default.target.value}) is claimed by "
                    f"more than one backend"
                )
                raise RuntimeError(msg)
            default_cells.add(default)
    missing = set(ALL_TOKENS) - seen
    if missing:
        names = ", ".join(sorted(t.__name__ for t in missing))
        msg = f"backend tokens missing from REGISTRY: {names}"
        raise RuntimeError(msg)
    expected_defaults = {
        BackendDefault(kind=kind, target=target) for kind in ResourceKind for target in Target
    }
    missing_defaults = expected_defaults - default_cells
    if missing_defaults:
        cells = ", ".join(
            sorted(f"({cell.kind.value}, {cell.target.value})" for cell in missing_defaults)
        )
        msg = f"default cells missing from REGISTRY: {cells}"
        raise RuntimeError(msg)


_registry_consistency_check()
