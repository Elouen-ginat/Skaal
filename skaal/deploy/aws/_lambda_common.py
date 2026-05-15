"""Shared scaffold builder for every Lambda-shaped AWS synth module.

The four backends ``lambda``, ``apigw-lambda``, ``eventbridge-lambda``,
and ``sqs-lambda-worker`` share the same boilerplate: ECR repository,
container image build/push, IAM role + policies, log group, and the
`aws.lambda_.Function` itself. The `build_lambda` helper packages all of
that and reads every tunable off `ctx.config.lambda_defaults` /
`ctx.config.ecr` / `ctx.config.iam` — there are no constants here that a
user can't override via `skaal.toml`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pulumi
import pulumi_aws as aws
import pulumi_docker as docker

from skaal.binding.model import BoundPlan
from skaal.deploy._protocol import SynthContext
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


def build_lambda(
    ctx: SynthContext[AwsConfig],
    *,
    timeout: int | None = None,
    memory_mb: int | None = None,
    extra_env: Mapping[str, Any] | None = None,
) -> LambdaScaffold:
    """Build the ECR repo + image + IAM + log group + Lambda for `ctx.resource`.

    Args:
        ctx: The typed synthesis context.
        timeout: Override the Lambda timeout. ``None`` falls through to
            `ctx.config.lambda_defaults.timeout_s`.
        memory_mb: Override the Lambda memory. ``None`` falls through to
            `ctx.config.lambda_defaults.memory_mb`.
        extra_env: Additional env vars to inject (merged on top of
            storage-peer vars).
    """
    cfg = ctx.config
    repository = _build_repository(ctx, cfg)
    image = _build_image(ctx, cfg, repository)
    role = _build_role(ctx, cfg)
    log_group = _build_log_group(ctx, cfg)
    function = _build_function(
        ctx,
        cfg,
        image=image,
        role=role,
        timeout=timeout if timeout is not None else cfg.lambda_defaults.timeout_s,
        memory_mb=memory_mb if memory_mb is not None else cfg.lambda_defaults.memory_mb,
        extra_env=extra_env,
    )
    return LambdaScaffold(
        function=function,
        role=role,
        log_group=log_group,
        image=image,
        repository=repository,
    )


def _build_repository(
    ctx: SynthContext[AwsConfig], cfg: AwsConfig
) -> aws.ecr.Repository:
    return aws.ecr.Repository(
        f"{ctx.pulumi_name}-repo",
        force_delete=cfg.ecr.force_delete,
        image_tag_mutability=cfg.ecr.image_tag_mutability,
        tags=ctx.tags,
    )


def _build_image(
    ctx: SynthContext[AwsConfig],
    cfg: AwsConfig,
    repository: aws.ecr.Repository,
) -> docker.Image:
    creds = aws.ecr.get_authorization_token_output(registry_id=repository.registry_id)
    return docker.Image(
        f"{ctx.pulumi_name}-image",
        image_name=pulumi.Output.concat(
            repository.repository_url, ":", ctx.bound.bound_fingerprint
        ),
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


def _build_role(ctx: SynthContext[AwsConfig], cfg: AwsConfig) -> aws.iam.Role:
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
    for backend_name in _policy_keys_for_plan(ctx.bound, cfg.iam.policies):
        aws.iam.RolePolicyAttachment(
            f"{ctx.pulumi_name}-role-{backend_name}",
            role=role.name,
            policy_arn=cfg.iam.policies[backend_name],
        )
    return role


def _build_log_group(
    ctx: SynthContext[AwsConfig], cfg: AwsConfig
) -> aws.cloudwatch.LogGroup:
    return aws.cloudwatch.LogGroup(
        f"{ctx.pulumi_name}-logs",
        name=pulumi.Output.concat("/aws/lambda/", ctx.pulumi_name),
        retention_in_days=cfg.lambda_defaults.log_retention_days,
        tags=ctx.tags,
    )


def _build_function(
    ctx: SynthContext[AwsConfig],
    cfg: AwsConfig,
    *,
    image: docker.Image,
    role: aws.iam.Role,
    timeout: int,
    memory_mb: int,
    extra_env: Mapping[str, Any] | None,
) -> aws.lambda_.Function:
    env = _merge_env_vars(ctx, extra_env)
    return aws.lambda_.Function(
        ctx.pulumi_name,
        package_type="Image",
        image_uri=image.image_name,
        role=role.arn,
        timeout=timeout,
        memory_size=memory_mb,
        environment=aws.lambda_.FunctionEnvironmentArgs(variables=env),
        tags=ctx.tags,
    )


def _policy_keys_for_plan(
    bound: BoundPlan, policies: Mapping[str, str]
) -> tuple[str, ...]:
    """Return the unique storage backend names present in `bound` that map to a policy."""
    seen: set[str] = set()
    for resource in bound.resources:
        if resource.external:
            continue
        if (
            resource.inferred.kind in _STORAGE_KINDS
            and resource.backend in policies
        ):
            seen.add(resource.backend)
    return tuple(sorted(seen))


def _merge_env_vars(
    ctx: SynthContext[AwsConfig], extra: Mapping[str, Any] | None
) -> dict[str, Any]:
    """Merge baseline env, storage-peer env vars, and `extra` overrides."""
    merged: dict[str, Any] = {
        "SKAAL_APP": ctx.bound.app,
        "SKAAL_ENV": ctx.env.name,
        "SKAAL_RESOURCE_ID": ctx.resource_id,
        "SKAAL_FINGERPRINT": ctx.bound.bound_fingerprint,
    }
    merged.update(
        {key: value for peer in ctx.peers.values() for key, value in peer.env_vars.items()}
    )
    if extra:
        merged.update(extra)
    return merged


__all__ = ["LambdaScaffold", "build_lambda"]
