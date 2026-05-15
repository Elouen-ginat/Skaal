"""Typed context + result objects threaded through every AWS synth module.

The AWS deploy package walks `BoundPlan.resources` and calls one
`synthesize(ctx)` function per non-external resource. Each call receives a
`SynthContext` carrying the bound plan, the resource being synthesised,
the active environment, the build-artefacts directory, and the
already-synthesised peer resources. The function returns a `SynthResult`
naming the principal Pulumi resource it produced, plus any env-var
references downstream compute resources should inject.

Both types are frozen dataclasses rather than pydantic models because
Pulumi `Resource` instances are not pydantic-friendly: their fields are
``pulumi.Output`` values whose schema is unknown until the engine resolves
them. A frozen dataclass with `tuple[Any, ...]` keeps the structural shape
strict without forcing every Pulumi `Output` through `arbitrary_types_allowed`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from skaal.binding.model import BoundPlan, BoundResource, Environment
from skaal.deploy.models import SkaalTags


@dataclass(frozen=True)
class SynthResult:
    """The typed return of an AWS synth function.

    Attributes:
        resource_id: The bound resource id this synth produced (mirrors
            ``ctx.resource.inferred.id``); used by the program driver to
            key the peer table.
        primary: The principal Pulumi resource (e.g. the
            ``aws.dynamodb.Table`` for a `DynamoDB` synth). Compute synth
            modules read this off ``ctx.peers`` to wire references.
        extras: Additional Pulumi resources created alongside the primary
            (IAM roles, log groups, event source mappings, …). Kept
            explicit so test assertions can count what was emitted.
        env_vars: Mapping of env-var name → Pulumi `Output` (or plain
            string) that downstream compute resources should inject into
            the Lambda container. E.g. a `DynamoDB` synth advertises
            ``{"SKAAL_TABLE_<slug>": table.name}``; the Lambda synth
            sweeps every peer's `env_vars` into ``Function.environment``.
    """

    resource_id: str
    primary: Any
    extras: tuple[Any, ...] = ()
    env_vars: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SynthContext:
    """Per-resource synthesis context handed to every AWS synth function.

    Attributes:
        bound: The full bound plan; synth functions read sibling
            resources here when they need to (e.g. Lambda env-var
            propagation from upstream stores).
        resource: The bound resource being synthesised.
        env: The active `Environment` (carries `region`, `target`, and
            `backends` for externals).
        build_dir: The directory `build_artefacts(...)` wrote to. Compute
            synth modules pass ``build_dir / resource_slug`` as the
            Docker build context.
        resource_slug: The filesystem-safe slug used as both the per-Lambda
            artefact subdirectory and the Pulumi resource-name prefix.
            Computed identically to `skaal.deploy.build._slug_for` so the
            program walks and the build tree stay in lock-step.
        peers: Mapping of resource-id → already-synthesised `SynthResult`
            for sibling resources. The program driver synthesises storage
            kinds before compute kinds so a Lambda synth function sees
            every store/blob/secret already in `peers`.
    """

    bound: BoundPlan
    resource: BoundResource
    env: Environment
    build_dir: Path
    resource_slug: str
    peers: Mapping[str, SynthResult]

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


__all__ = ["SynthContext", "SynthResult"]
