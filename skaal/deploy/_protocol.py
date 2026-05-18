"""Cross-target deploy protocol — shared types and the `DeployTarget` interface.

Every deploy target (`skaal.deploy.aws`, eventual `skaal.deploy.gcp`,
`skaal.deploy.azure`, …) plugs into the same protocol declared here. The
program driver in `skaal.deploy.program` does not know about any
particular cloud: it asks the registry for the `DeployTarget` matching
`env.target`, then walks `BoundPlan.resources` and dispatches via the
target's `lookup_synth` method.

The four types in this module form the contract:

- `SynthContext[ConfigT]` — per-resource context handed to a synth
  function. Carries the typed config for the active target so synths
  read structured fields instead of class literals.
- `SynthResult` — the typed return of a synth function.
- `SynthSpec` — metadata each synth module exports (the backend names it
  handles plus which resource kinds it supports). Lets the target's
  registration step validate that the synth covers the kinds the
  binder might assign to it.
- `DeployTarget` — the Protocol every target satisfies.
- `TargetConfig` — base pydantic model for per-target typed config
  trees; each target subclasses with its own field set.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Generic,
    Protocol,
    TypeVar,
    cast,
    runtime_checkable,
)

from pydantic import BaseModel, ConfigDict, Field, model_validator

from skaal.backends._base import Backend
from skaal.binding.model import Target
from skaal.binding.registry import lookup, lookup_token
from skaal.deploy.models import SkaalTags
from skaal.errors import UnknownBackendError
from skaal.inference.model import ResourceKind

if TYPE_CHECKING:
    from skaal.binding.model import Environment, Plan, PlannedResource


class TargetConfig(BaseModel):
    """Base pydantic model for per-target typed config trees.

    Each target subclasses this with its own field set (e.g. `AwsConfig`
    aggregates `AwsLambdaConfig`, `DynamoDBConfig`, …). The class
    deliberately has no fields — concrete targets define everything.
    Subclasses freeze themselves so config drift after `from_env(...)`
    is a type error.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


ConfigT = TypeVar("ConfigT", bound=TargetConfig)
ConsoleUrlResolver = Callable[[Mapping[str, Any], str | None], str]


@dataclass(frozen=True)
class SynthResult:
    """The typed return of a synth function.

    Attributes:
        resource_id: The bound resource id this synth produced (mirrors
            ``ctx.resource.inferred.id``); the driver keys the peer table
            on this value.
        primary: The principal Pulumi resource (e.g. the
            ``aws.dynamodb.Table`` for a DynamoDB synth). Compute synth
            modules read this off ``ctx.peers`` to wire references.
        extras: Additional Pulumi resources created alongside the primary
            (IAM roles, log groups, event source mappings, …). Kept
            explicit so test assertions can count what was emitted.
        env_vars: Mapping of env-var name → Pulumi `Output` (or plain
            string) that downstream compute resources should inject into
            their runtime container. A `DynamoDB` synth advertises
            ``{"SKAAL_TABLE_<slug>": table.name}``; the Lambda synth
            sweeps every peer's ``env_vars`` into its `Function.environment`.
    """

    resource_id: str
    primary: Any
    extras: tuple[Any, ...] = ()
    env_vars: Mapping[str, Any] = field(default_factory=lambda: cast(Mapping[str, Any], {}))


class WherePreference(BaseModel):
    """One ordered deployed resource preference for `skaal where`.

    When a synth emits multiple Pulumi resources for one Skaal resource,
    `skaal where` needs a stable way to pick which exported provider type
    should represent that resource in console lookups. Higher `priority`
    wins; ties keep registration order. A priority of `0` is the lowest
    built-in/default priority level.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: ResourceKind
    provider_type: str
    priority: int = 0


class WhereSpec(BaseModel):
    """Optional `skaal where` metadata exported by a `SynthModule`.

    `preferences` tells `where` which Pulumi resource types should be
    preferred for each Skaal `ResourceKind`. `console_url_resolvers`
    converts a provider type's exported Pulumi outputs into a console URL.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    preferences: tuple[WherePreference, ...] = ()
    console_url_resolvers: Mapping[str, ConsoleUrlResolver] = Field(default_factory=dict)


@dataclass(frozen=True)
class SynthContext(Generic[ConfigT]):
    """Per-resource synthesis context handed to every synth function.

    Generic over the target's `TargetConfig` subclass so synth code reads
    its tunables off `ctx.config.<section>` with static types intact.

    Attributes:
        bound: The full bound plan; synth functions read sibling
            resources here when they need to.
        resource: The bound resource being synthesised.
        env: The active `Environment` (carries `region`, `target`, and
            `backends` for externals).
        build_dir: The directory `build_artefacts(...)` wrote to.
        resource_slug: The filesystem-safe slug used as both the per-Lambda
            artefact subdirectory and the Pulumi resource-name prefix.
        peers: Mapping of resource-id → already-synthesised `SynthResult`.
            Storage kinds are synthesised before compute kinds so a
            compute synth sees every storage peer in `peers`.
        config: The typed config tree for this target — overridable via
            `Environment.backends[<target_name>].options` from `skaal.toml`.
    """

    bound: Plan
    resource: PlannedResource
    env: Environment
    build_dir: Path
    resource_slug: str
    peers: Mapping[str, SynthResult]
    config: ConfigT

    @property
    def resource_id(self) -> str:
        """Convenience accessor for ``self.resource.inferred.id``."""
        return self.resource.inferred.id

    @property
    def tags(self) -> dict[str, str]:
        """Skaal tags for this resource, ready for Pulumi `tags=` kwargs."""
        return SkaalTags.for_resource(
            self.resource, self.env, self.bound.app_fingerprint
        ).as_mapping()

    @property
    def pulumi_name(self) -> str:
        """Stable Pulumi resource-name prefix derived from `resource_slug`."""
        return f"skaal-{self.resource_slug}"

    @property
    def slug_key(self) -> str:
        """Upper-case underscore form of `resource_slug` for env-var keys."""
        return self.resource_slug.replace("-", "_").upper()


SynthFn = Callable[[SynthContext[Any]], SynthResult]


def _backend_name_for_token(token: type[Backend[Any]]) -> str:
    """Return the canonical backend name for `token`.

    Built-in and already-registered plugin backends resolve through the
    binding registry; late-bound plugin synths can still fall back to the
    token's class metadata before registration happens.
    """
    try:
        return lookup_token(token).name
    except UnknownBackendError:
        return token.name


def _kinds_for_token(token: type[Backend[Any]]) -> frozenset[ResourceKind]:
    """Return the `ResourceKind`s hosted by `token`.

    Prefer the binding registry when the backend is registered so deploy and
    binding metadata share one source of truth. Late-bound plugin synths keep
    working by falling back to the token class until the plugin registers the
    corresponding `BackendEntry`.
    """
    try:
        return lookup_token(token).kinds
    except UnknownBackendError:
        return frozenset(ResourceKind(kind) for kind in token.kinds)


def _normalize_synth_tokens(
    raw: object,
) -> tuple[type[Backend[Any]], ...]:
    """Normalize legacy backend names or backend tokens into backend tokens."""
    if not isinstance(raw, (tuple, list)):
        raise TypeError("`SynthSpec.tokens` must be a sequence of backend tokens.")
    tokens: list[type[Backend[Any]]] = []
    for item in raw:
        if isinstance(item, str):
            tokens.append(lookup(item).token_class)
            continue
        if isinstance(item, type) and issubclass(item, Backend):
            tokens.append(item)
            continue
        raise TypeError(
            "`SynthSpec.tokens` items must be `Backend` subclasses or legacy "
            f"backend name strings; got {item!r}."
        )
    if not tokens:
        raise ValueError("`SynthSpec.tokens` must name at least one backend.")
    return tuple(tokens)


def _kinds_for_synth_tokens(tokens: tuple[type[Backend[Any]], ...]) -> frozenset[ResourceKind]:
    """Return the union of `ResourceKind`s hosted by `tokens`."""
    return frozenset(kind for token in tokens for kind in _kinds_for_token(token))


class SynthSpec(BaseModel):
    """Per-class metadata declared by every `SynthModule` subclass.

    Each `SynthModule` subclass declares `SPEC: ClassVar[SynthSpec]`
    listing the backend tokens it serves; backend names and resource
    kinds are derived from those tokens so deploy-side metadata stays in
    lock-step with the binding registry. `BaseDeployTarget.from_classes(...)`
    walks each class's `SPEC` to build the dispatch table; the binder and
    the deploy walker both rely on the same backend token metadata.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Backend token classes this synth handles. Pydantic's schema
    # generation rejects the parameterised `Backend[Any]` form here (same
    # limitation handled in `skaal.binding.registry.BackendEntry`), so we
    # store the bare `Backend` and expose the fully-typed `token_classes`
    # property below for static-typing consumers.
    tokens: tuple[
        type[Backend],  # pyright: ignore[reportMissingTypeArgument] - Pydantic rejects parameterised generics in schema generation
        ...,
    ]
    description: str = ""
    where: WhereSpec | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_backend_metadata(cls, data: object) -> object:
        """Accept token-based metadata and coerce legacy name-based input."""
        if not isinstance(data, dict):
            return data
        raw_tokens = data.pop("tokens", None)
        raw_backends = data.pop("backends", None)
        if raw_tokens is not None and raw_backends is not None:
            raise ValueError("Provide only one of `tokens` or `backends` to `SynthSpec`.")
        if raw_tokens is None and raw_backends is None:
            raise ValueError("`SynthSpec` requires `tokens` (or legacy `backends`).")
        tokens = _normalize_synth_tokens(raw_tokens if raw_tokens is not None else raw_backends)
        raw_kinds = data.pop("kinds", None)
        derived_kinds = _kinds_for_synth_tokens(tokens)
        provided_kinds = frozenset(raw_kinds) if raw_kinds is not None else None
        if provided_kinds is not None and provided_kinds != derived_kinds:
            expected = ", ".join(sorted(kind.value for kind in derived_kinds))
            provided = ", ".join(sorted(kind.value for kind in provided_kinds))
            raise ValueError(
                "`SynthSpec.kinds` is derived from the supplied backend tokens and "
                f"must match them exactly. Expected: [{expected}]. Provided: [{provided}]."
            )
        return {**data, "tokens": tokens}

    @property
    def token_classes(self) -> tuple[type[Backend[Any]], ...]:
        """Return `tokens` as fully-parameterised backend token classes."""
        return cast("tuple[type[Backend[Any]], ...]", self.tokens)

    @property
    def backends(self) -> tuple[str, ...]:
        """Return the backend names derived from `tokens`."""
        return tuple(_backend_name_for_token(token) for token in self.token_classes)

    @property
    def kinds(self) -> frozenset[ResourceKind]:
        """Return the union of `ResourceKind`s hosted by `tokens`."""
        return _kinds_for_synth_tokens(self.token_classes)


class SynthModule(Generic[ConfigT], ABC):
    """Abstract base for one synth contribution.

    Subclasses declare `SPEC` as a `ClassVar[SynthSpec]` (which backend
    names + resource kinds they serve) and override `synthesize(ctx)`
    to emit Pulumi resources. Concrete subclasses are usually stateless
    singletons — `BaseDeployTarget.from_classes(...)` instantiates each
    once and stores the bound `synthesize` method in its dispatch table.

    The `Generic[ConfigT]` parameter ties a synth class to its target's
    `TargetConfig` subclass, so `class DynamoDBSynth(SynthModule[AwsConfig])`
    gets `ctx.config: AwsConfig` typed automatically.

    Adding a shared scaffold (e.g. the Lambda image/IAM/log-group
    boilerplate) is a normal subclass-with-helpers pattern; the four
    `LambdaSynth` subclasses in `skaal/deploy/aws/_lambda.py` exercise
    this directly.
    """

    SPEC: ClassVar[SynthSpec]

    @abstractmethod
    def synthesize(self, ctx: SynthContext[ConfigT]) -> SynthResult:
        """Emit the Pulumi resources for `ctx.resource`."""


@runtime_checkable
class DeployTarget(Protocol):
    """The contract every deploy target satisfies (ADR 028 §6.2 §6.6).

    Each `skaal.deploy.<target>/__init__.py` constructs one
    `DeployTarget` and calls `register_target(...)`. The driver in
    `skaal.deploy.program` looks up the right target by `env.target` and
    never reaches into a target package directly.
    """

    target: ClassVar[Target]

    def lookup_synth(self, backend_name: str) -> SynthFn | None:
        """Return the synth function for `backend_name`, or ``None``."""
        ...

    def register_synth(self, synth: SynthModule[Any]) -> None:
        """Register a plugin-contributed synth on this target.

        Implementations should be idempotent for the same instance and
        raise `SkaalDeployError` on a name collision with a different
        instance.
        """
        ...

    def supported_backends(self) -> frozenset[str]:
        """The set of backend names this target can synthesise."""
        ...

    def default_config(self) -> TargetConfig:
        """The bare-defaults config for this target."""
        ...

    def config_for(self, env: Environment) -> TargetConfig:
        """Load the typed config for `env`, overlaying any TOML overrides."""
        ...

    def stack_name(self, bound: Plan, env: Environment) -> str:
        """The Pulumi stack name to use for `(bound, env)`."""
        ...

    def stack_config(self, env: Environment) -> Mapping[str, str]:
        """Pulumi stack-config entries (region, project, …)."""
        ...

    def required_extras(self) -> tuple[str, ...]:
        """Importable module names this target needs (for clean errors)."""
        ...

    def where_console_url_resolvers(self) -> Mapping[str, ConsoleUrlResolver]:
        """Built-in `skaal where` console URL resolvers keyed by provider type."""
        ...

    def where_resource_type_preferences(self) -> Mapping[ResourceKind, tuple[str, ...]]:
        """Built-in `skaal where` provider-type orderings keyed by resource kind."""
        ...


__all__ = [
    "ConfigT",
    "ConsoleUrlResolver",
    "DeployTarget",
    "SynthContext",
    "SynthFn",
    "SynthModule",
    "SynthResult",
    "SynthSpec",
    "TargetConfig",
    "WherePreference",
    "WhereSpec",
]
