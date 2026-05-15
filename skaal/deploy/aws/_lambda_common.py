"""Shared helpers used by every Lambda-shaped AWS synth module.

The four backends ``lambda``, ``apigw-lambda``, ``eventbridge-lambda``,
and ``sqs-lambda-worker`` all need the same scaffold:

1. An ECR repository to push the container image to (one per resource —
   Phase 6 may consolidate across the stack).
2. A `docker.Image` built from ``build_dir/<slug>/`` and pushed to that repo.
3. An IAM role with the basic Lambda execution policy plus broad
   managed policies for any storage backend present in the bound plan
   (the bytecode-edge walker in Phase 6 will tighten this).
4. A CloudWatch log group with a sensible retention.
5. The `aws.lambda_.Function` itself, pointing at the image and
   populated with env vars contributed by upstream storage peers.

Centralising the scaffold keeps each compute synth module short — they
only specify the *event source* (APIGW, EventBridge, SQS, none) and let
this module own the boilerplate.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pulumi
import pulumi_aws as aws
import pulumi_docker as docker

from skaal.binding.model import BoundPlan
from skaal.deploy.aws._context import SynthContext
from skaal.inference.model import ResourceKind


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


_STORAGE_KIND_TO_POLICY: Mapping[str, str] = {
    "dynamodb": "arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess",
    "s3": "arn:aws:iam::aws:policy/AmazonS3FullAccess",
    "postgres": "arn:aws:iam::aws:policy/AmazonRDSDataFullAccess",
    "redis": "arn:aws:iam::aws:policy/AmazonElastiCacheFullAccess",
    "redis-channel": "arn:aws:iam::aws:policy/AmazonElastiCacheFullAccess",
    "sqs": "arn:aws:iam::aws:policy/AmazonSQSFullAccess",
    "aws-secrets-manager": "arn:aws:iam::aws:policy/SecretsManagerReadWrite",
}


_STORAGE_KINDS: frozenset[ResourceKind] = frozenset(
    {
        ResourceKind.STORE,
        ResourceKind.RELATIONAL,
        ResourceKind.BLOB,
        ResourceKind.CHANNEL,
        ResourceKind.SECRET,
    }
)


_LAMBDA_TRUST_POLICY = """
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Action": "sts:AssumeRole",
            "Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"}
        }
    ]
}
""".strip()


def build_lambda(
    ctx: SynthContext,
    *,
    timeout: int = 30,
    memory_mb: int = 512,
    extra_env: Mapping[str, Any] | None = None,
) -> LambdaScaffold:
    """Build the ECR repo + image + IAM + log group + Lambda for `ctx.resource`.

    Args:
        ctx: The synthesis context.
        timeout: Lambda function timeout in seconds.
        memory_mb: Lambda memory allocation in MiB.
        extra_env: Additional env vars (merged on top of storage-peer vars).
    """
    repository = aws.ecr.Repository(
        f"{ctx.pulumi_name}-repo",
        force_delete=True,
        image_tag_mutability="MUTABLE",
        tags=ctx.tags,
    )

    creds = aws.ecr.get_authorization_token_output(registry_id=repository.registry_id)
    image = docker.Image(
        f"{ctx.pulumi_name}-image",
        image_name=pulumi.Output.concat(
            repository.repository_url, ":", ctx.bound.bound_fingerprint
        ),
        build=docker.DockerBuildArgs(
            context=str(ctx.build_dir / ctx.resource_slug),
            dockerfile=str(ctx.build_dir / ctx.resource_slug / "Dockerfile"),
            platform="linux/amd64",
        ),
        registry=docker.RegistryArgs(
            server=repository.repository_url,
            username=creds.user_name,
            password=creds.password,
        ),
    )

    role = aws.iam.Role(
        f"{ctx.pulumi_name}-role",
        assume_role_policy=_LAMBDA_TRUST_POLICY,
        tags=ctx.tags,
    )
    aws.iam.RolePolicyAttachment(
        f"{ctx.pulumi_name}-role-basic",
        role=role.name,
        policy_arn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
    )
    for backend_name in _policy_arns_for_plan(ctx.bound):
        aws.iam.RolePolicyAttachment(
            f"{ctx.pulumi_name}-role-{backend_name}",
            role=role.name,
            policy_arn=_STORAGE_KIND_TO_POLICY[backend_name],
        )

    log_group = aws.cloudwatch.LogGroup(
        f"{ctx.pulumi_name}-logs",
        name=pulumi.Output.concat(
            "/aws/lambda/", ctx.pulumi_name
        ),
        retention_in_days=14,
        tags=ctx.tags,
    )

    env = _merge_env_vars(ctx, extra_env)
    function = aws.lambda_.Function(
        ctx.pulumi_name,
        package_type="Image",
        image_uri=image.image_name,
        role=role.arn,
        timeout=timeout,
        memory_size=memory_mb,
        environment=aws.lambda_.FunctionEnvironmentArgs(variables=env),
        tags=ctx.tags,
    )

    return LambdaScaffold(
        function=function,
        role=role,
        log_group=log_group,
        image=image,
        repository=repository,
    )


def _policy_arns_for_plan(bound: BoundPlan) -> tuple[str, ...]:
    """Return the unique storage backend names present in `bound` that map to a policy."""
    seen: set[str] = set()
    for resource in bound.resources:
        if resource.external:
            continue
        if (
            resource.inferred.kind in _STORAGE_KINDS
            and resource.backend in _STORAGE_KIND_TO_POLICY
        ):
            seen.add(resource.backend)
    return tuple(sorted(seen))


def _merge_env_vars(
    ctx: SynthContext, extra: Mapping[str, Any] | None
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
