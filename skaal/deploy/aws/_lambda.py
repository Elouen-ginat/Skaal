"""Lambda-shaped synth class hierarchy.

The four AWS backends that ship a Lambda — `lambda`, `apigw-lambda`,
`eventbridge-lambda`, `sqs-lambda-worker` — share the same ECR + image +
IAM + log group + function scaffold. That common scaffold lives on the
`LambdaSynth` base class; each concrete subclass overrides
`_event_source(...)` (and timeout / memory defaults if it needs to) to
attach its event trigger.

`LambdaSynth` is abstract — it declares no `SPEC` so `from_classes(...)`
won't pick it up. The four concrete subclasses live in their own files
(`lambda_fn.py`, `apigw_lambda.py`, `eventbridge.py`, `sqs_worker.py`)
and inherit from this base.

The `_pre_scaffold(ctx)` hook covers the SQS-worker case: a synth that
needs a resource available *before* the Lambda is constructed (so its
URL can be injected into the Lambda's env). The returned `PreScaffold`
flows into both the scaffold builder (`extra_env=pre.env_vars`) and the
`_event_source(ctx, scaffold, pre)` hook (via `pre.payload`) so the
post-scaffold wiring step can reference the pre-built resource.
"""

from __future__ import annotations

import hashlib
import os
from abc import ABC
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import pulumi
import pulumi_aws as aws
import pulumi_docker as docker

from skaal.binding.model import Plan
from skaal.deploy._protocol import SynthContext, SynthModule, SynthResult
from skaal.deploy.aws._config import AwsConfig
from skaal.inference.model import ResourceKind

_STORAGE_KINDS: frozenset[ResourceKind] = frozenset(
    {
        ResourceKind.STORE,
        ResourceKind.RELATIONAL,
        ResourceKind.BLOB,
        ResourceKind.CHANNEL,
        ResourceKind.SECRET,
    }
)


@dataclass(frozen=True)
class LambdaScaffold:
    """The Pulumi resources every compute-side Lambda synth produces."""

    function: aws.lambda_.Function
    role: aws.iam.Role
    log_group: aws.cloudwatch.LogGroup
    image: docker.Image
    repository: aws.ecr.Repository

    def as_extras(self) -> tuple[Any, ...]:
        """Return the non-primary scaffolding resources as a tuple."""
        return (self.role, self.log_group, self.image, self.repository)


@dataclass(frozen=True)
class PreScaffold:
    """Resources and env vars produced *before* the Lambda scaffold.

    Synth subclasses that need a resource available at Lambda-construction
    time (e.g. an SQS queue whose URL must be in the Lambda's environment
    so the handler can re-enqueue work) return this from
    `_pre_scaffold(ctx)`. The orchestrator:

    - prepends `resources` to `SynthResult.extras`,
    - injects `env_vars` into the scaffold's `Function.environment`,
    - and re-exposes the whole `PreScaffold` to
      `_event_source(ctx, scaffold, pre)` so the post-scaffold wiring
      step can reference the pre-built resources via `pre.payload`.

    `payload` is a subclass-defined bag for any cross-hook state that
    isn't already captured in `resources` / `env_vars` (typically the
    same Pulumi resource references the subclass needs back from the
    `_event_source` callback).
    """

    resources: tuple[Any, ...] = ()
    env_vars: Mapping[str, Any] = field(default_factory=lambda: cast(Mapping[str, Any], {}))
    payload: Any = None


class LambdaSynth(SynthModule[AwsConfig], ABC):
    """Abstract base for every Lambda-shaped AWS synth.

    Subclasses override `_event_source(ctx, scaffold, pre)` to attach an
    event trigger (APIGW, EventBridge, SQS event-source-mapping, …).
    `_timeout_s(ctx)` and `_memory_mb(ctx)` are overrideable so the
    ASGI / JOB variants can pick their own defaults from `AwsConfig`.
    Subclasses that need a resource available before the Lambda is
    constructed override `_pre_scaffold(ctx)` instead of overriding the
    whole `synthesize(ctx)` method.
    """

    # No `SPEC` here — `LambdaSynth` is abstract and must not appear in
    # any target's class list directly. Concrete subclasses declare it.

    def synthesize(self, ctx: SynthContext[AwsConfig]) -> SynthResult:
        pre = self._pre_scaffold(ctx)
        scaffold = self._build_scaffold(ctx, extra_env=pre.env_vars)
        event_resources = self._event_source(ctx, scaffold, pre)
        return SynthResult(
            resource_id=ctx.resource_id,
            primary=scaffold.function,
            extras=(*pre.resources, *scaffold.as_extras(), *event_resources),
            env_vars=self._env_vars(ctx, scaffold, pre),
        )

    def _build_scaffold(
        self,
        ctx: SynthContext[AwsConfig],
        *,
        extra_env: Mapping[str, Any] | None = None,
    ) -> LambdaScaffold:
        cfg = ctx.config
        repository = self._build_repository(ctx, cfg)
        image = self._build_image(ctx, cfg, repository)
        role = self._build_role(ctx, cfg)
        log_group = self._build_log_group(ctx, cfg)
        function = self._build_function(
            ctx,
            cfg,
            image=image,
            role=role,
            extra_env=extra_env,
        )
        return LambdaScaffold(
            function=function,
            role=role,
            log_group=log_group,
            image=image,
            repository=repository,
        )

    # -- Overridable knobs ----------------------------------------------------

    def _timeout_s(self, ctx: SynthContext[AwsConfig]) -> int:
        overrides = ctx.resource.inferred.overrides
        if overrides.timeout_s:
            return int(overrides.timeout_s)
        return ctx.config.lambda_defaults.timeout_s

    def _memory_mb(self, ctx: SynthContext[AwsConfig]) -> int:
        overrides = ctx.resource.inferred.overrides
        return overrides.memory_mb or ctx.config.lambda_defaults.memory_mb

    def _pre_scaffold(self, ctx: SynthContext[AwsConfig]) -> PreScaffold:
        """Default: no pre-scaffold resources or env vars."""
        return PreScaffold()

    def _event_source(
        self,
        ctx: SynthContext[AwsConfig],
        scaffold: LambdaScaffold,
        pre: PreScaffold,
    ) -> tuple[Any, ...]:
        """Default: no event source attached."""
        return ()

    def _env_vars(
        self,
        ctx: SynthContext[AwsConfig],
        scaffold: LambdaScaffold,
        pre: PreScaffold,
    ) -> Mapping[str, Any]:
        """Default: re-export the pre-scaffold env vars to downstream peers.

        SQS worker peers see `SKAAL_JOB_<slug>_URL` here, so a separate
        FUNCTION resource that wants to enqueue work picks the URL up
        via the standard peer-env-var mechanism in `_merge_env_vars`.
        """
        return dict(pre.env_vars)

    # -- Internal Pulumi resource builders ------------------------------------

    def _build_repository(self, ctx: SynthContext[AwsConfig], cfg: AwsConfig) -> aws.ecr.Repository:
        return aws.ecr.Repository(
            _repository_name(f"{ctx.pulumi_name}-repo"),
            force_delete=cfg.ecr.force_delete,
            image_tag_mutability=cfg.ecr.image_tag_mutability,
            tags=ctx.tags,
        )

    def _build_image(
        self,
        ctx: SynthContext[AwsConfig],
        cfg: AwsConfig,
        repository: aws.ecr.Repository,
    ) -> docker.Image:
        creds = aws.ecr.get_authorization_token_output(registry_id=repository.registry_id)
        image_tag = _artifact_tag_for_dir(ctx.build_dir / ctx.resource_slug)
        return docker.Image(
            f"{ctx.pulumi_name}-image",
            image_name=pulumi.Output.concat(repository.repository_url, ":", image_tag),
            build=docker.DockerBuildArgs(
                context=str(ctx.build_dir / ctx.resource_slug),
                dockerfile=str(ctx.build_dir / ctx.resource_slug / "Dockerfile"),
                platform=cfg.ecr.platform,
            ),
            registry=docker.RegistryArgs(
                server=repository.repository_url,
                username=creds.user_name,
                password=creds.password,
            ),
        )

    def _build_role(self, ctx: SynthContext[AwsConfig], cfg: AwsConfig) -> aws.iam.Role:
        role = aws.iam.Role(
            f"{ctx.pulumi_name}-role",
            assume_role_policy=cfg.iam.lambda_trust_policy,
            tags=ctx.tags,
        )
        aws.iam.RolePolicyAttachment(
            f"{ctx.pulumi_name}-role-basic",
            role=role.name,
            policy_arn=cfg.iam.basic_execution_role_arn,
        )
        for backend_name in self._policy_keys_for_plan(ctx.bound, cfg.iam.policies):
            aws.iam.RolePolicyAttachment(
                f"{ctx.pulumi_name}-role-{backend_name}",
                role=role.name,
                policy_arn=cfg.iam.policies[backend_name],
            )
        return role

    def _build_log_group(
        self, ctx: SynthContext[AwsConfig], cfg: AwsConfig
    ) -> aws.cloudwatch.LogGroup:
        return aws.cloudwatch.LogGroup(
            f"{ctx.pulumi_name}-logs",
            name=pulumi.Output.concat("/aws/lambda/", ctx.pulumi_name),
            retention_in_days=cfg.lambda_defaults.log_retention_days,
            tags=ctx.tags,
        )

    def _build_function(
        self,
        ctx: SynthContext[AwsConfig],
        cfg: AwsConfig,
        *,
        image: docker.Image,
        role: aws.iam.Role,
        extra_env: Mapping[str, Any] | None,
    ) -> aws.lambda_.Function:
        env = self._merge_env_vars(ctx, extra_env)
        return aws.lambda_.Function(
            ctx.pulumi_name,
            package_type="Image",
            image_uri=image.image_name,
            role=role.arn,
            timeout=self._timeout_s(ctx),
            memory_size=self._memory_mb(ctx),
            environment=aws.lambda_.FunctionEnvironmentArgs(variables=env),
            tags=ctx.tags,
        )

    @staticmethod
    def _policy_keys_for_plan(bound: Plan, policies: Mapping[str, str]) -> tuple[str, ...]:
        """Return the unique storage backend names present in `bound`."""
        seen: set[str] = set()
        for resource in bound.resources:
            if resource.external:
                continue
            if resource.inferred.kind in _STORAGE_KINDS and resource.backend in policies:
                seen.add(resource.backend)
        return tuple(sorted(seen))

    @staticmethod
    def _merge_env_vars(
        ctx: SynthContext[AwsConfig], extra: Mapping[str, Any] | None
    ) -> dict[str, Any]:
        """Merge baseline env, storage-peer env vars, and per-call overrides."""
        merged: dict[str, Any] = {
            "SKAAL_APP": ctx.bound.app,
            "SKAAL_ENV": ctx.env.name,
            "SKAAL_RESOURCE_ID": ctx.resource_id,
            "SKAAL_FINGERPRINT": ctx.bound.bound_fingerprint,
        }
        merged.update(
            {key: value for peer in ctx.peers.values() for key, value in peer.env_vars.items()}
        )
        runtime_wire = os.environ.get("SKAAL_RUNTIME_WIRE")
        if runtime_wire is not None:
            merged["SKAAL_RUNTIME_WIRE"] = runtime_wire
        if extra:
            merged.update(extra)
        return merged


def _artifact_tag_for_dir(resource_dir: Path) -> str:
    """Return a stable image tag derived from one rendered Lambda artifact dir."""
    digest = hashlib.sha256()
    for path in sorted(candidate for candidate in resource_dir.rglob("*") if candidate.is_file()):
        relative = path.relative_to(resource_dir).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:16]


def _repository_name(name: str) -> str:
    """Return an ECR-compatible repository name derived from a Pulumi prefix."""
    sanitized = "".join(char if char.isalnum() else "-" for char in name.lower())
    collapsed = "-".join(part for part in sanitized.split("-") if part)
    return collapsed or "skaal"


__all__ = ["LambdaScaffold", "LambdaSynth", "PreScaffold"]
