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
    runtime_checkable,
)

from pydantic import BaseModel, ConfigDict

from skaal.binding.model import Target
from skaal.deploy.models import SkaalTags
from skaal.inference.model import ResourceKind

if TYPE_CHECKING:
    from skaal.binding.model import BoundPlan, BoundResource, Environment


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
    env_vars: Mapping[str, Any] = field(default_factory=dict)


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

    bound: BoundPlan
    resource: BoundResource
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


class SynthSpec(BaseModel):
    """Per-class metadata declared by every `SynthModule` subclass.

    Each `SynthModule` subclass declares `SPEC: ClassVar[SynthSpec]`
    listing the backend names it serves and the resource kinds it
    supports. `BaseDeployTarget.from_classes(...)` walks each class's
    `SPEC` to build the dispatch table; the binder and the deploy
    walker both rely on this metadata to validate themselves.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    backends: tuple[str, ...]
    kinds: frozenset[ResourceKind]
    description: str = ""


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

    def stack_name(self, bound: BoundPlan, env: Environment) -> str:
        """The Pulumi stack name to use for `(bound, env)`."""
        ...

    def stack_config(self, env: Environment) -> Mapping[str, str]:
        """Pulumi stack-config entries (region, project, …)."""
        ...

    def required_extras(self) -> tuple[str, ...]:
        """Importable module names this target needs (for clean errors)."""
        ...


__all__ = [
    "ConfigT",
    "DeployTarget",
    "SynthContext",
    "SynthFn",
    "SynthModule",
    "SynthResult",
    "SynthSpec",
    "TargetConfig",
]
