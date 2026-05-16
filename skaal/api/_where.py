"""Resolve deployed resources to cloud-console URLs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from skaal.binding.model import BoundPlan, BoundResource, Environment, Target
from skaal.deploy import get_target
from skaal.errors import MissingExtraError, SkaalDeployError
from skaal.inference.model import ResourceKind

_AWS_TYPE_PREFERENCE: dict[ResourceKind, tuple[str, ...]] = {
    ResourceKind.STORE: (
        "aws:dynamodb/table:Table",
        "aws:elasticache/replicationGroup:ReplicationGroup",
    ),
    ResourceKind.BLOB: ("aws:s3/bucketV2:BucketV2",),
    ResourceKind.CHANNEL: (
        "aws:sqs/queue:Queue",
        "aws:elasticache/replicationGroup:ReplicationGroup",
    ),
    ResourceKind.RELATIONAL: ("aws:rds/instance:Instance",),
    ResourceKind.FUNCTION: ("aws:lambda/function:Function",),
    ResourceKind.ASGI_SERVICE: (
        "aws:apigatewayv2/api:Api",
        "aws:lambda/function:Function",
    ),
    ResourceKind.SCHEDULE: (
        "aws:cloudwatch/eventRule:EventRule",
        "aws:lambda/function:Function",
    ),
    ResourceKind.JOB: (
        "aws:sqs/queue:Queue",
        "aws:lambda/function:Function",
    ),
    ResourceKind.SECRET: ("aws:secretsmanager/secret:Secret",),
}


@dataclass(frozen=True)
class WhereHit:
    """One resolved deployed-resource location."""

    resource: BoundResource
    stack_name: str
    provider_type: str
    console_url: str
    physical_id: str | None


def resolve_where(resource_id: str, bound: BoundPlan, env: Environment) -> WhereHit:
    """Resolve `resource_id` to its cloud-console URL.

    Args:
        resource_id: Bound resource id to resolve.
        bound: Bound plan for the target app/environment.
        env: Active environment.

    Returns:
        The resolved deployed-resource location.

    Raises:
        ValueError: If the resource is unknown, external, unsupported, or not found in state.
        MissingExtraError: If the deploy extras needed to inspect the stack are missing.
        SkaalDeployError: If the stack export cannot be read.
    """
    resource = _bound_resource(resource_id, bound)
    if resource.external:
        msg = f"Resource {resource_id!r} is external and has no Skaal-managed deployed resource."
        raise ValueError(msg)
    if env.target is not Target.AWS:
        msg = (
            f"`skaal where` currently supports target {Target.AWS.value!r} only; "
            f"env {env.name!r} targets {env.target.value!r}."
        )
        raise ValueError(msg)

    stack_name = _stack_name(bound, env)
    deployment = _load_stack_deployment(bound, env, stack_name=stack_name)
    deployed = _select_deployed_resource(resource, deployment)
    console_url = _aws_console_url(deployed, region=env.region)
    return WhereHit(
        resource=resource,
        stack_name=stack_name,
        provider_type=str(_field(deployed, "type") or ""),
        console_url=console_url,
        physical_id=_physical_id(deployed),
    )


def _bound_resource(resource_id: str, bound: BoundPlan) -> BoundResource:
    for resource in bound.resources:
        if resource.inferred.id == resource_id:
            return resource
    known_ids = ", ".join([resource.inferred.id for resource in bound.resources[:5]])
    suffix = ", ..." if len(bound.resources) > 5 else ""
    raise ValueError(
        f"Could not resolve {resource_id!r} to a known resource id. "
        f"Expected one of: {known_ids or '(no resources)'}{suffix}."
    )


def _stack_name(bound: BoundPlan, env: Environment) -> str:
    try:
        target = get_target(env.target)
    except Exception:
        return f"{bound.app}-{env.name}"
    return target.stack_name(bound, env)


def _load_stack_deployment(
    bound: BoundPlan, env: Environment, *, stack_name: str
) -> Mapping[str, Any] | object:
    try:
        from pulumi import automation as auto
    except ImportError as exc:
        raise MissingExtraError(
            "`skaal where` requires the Pulumi SDKs. Install them with "
            "`pip install 'skaal[deploy,aws]'`."
        ) from exc

    project_name = bound.app or "skaal"
    try:
        stack = auto.select_stack(
            stack_name=stack_name,
            project_name=project_name,
            program=lambda: None,
        )
    except Exception as exc:  # pragma: no cover - integration path
        raise SkaalDeployError(
            f"Could not open Pulumi stack {stack_name!r} for project {project_name!r}: {exc}"
        ) from exc

    try:
        exported = stack.export_stack()
    except Exception as exc:  # pragma: no cover - integration path
        raise SkaalDeployError(f"Could not export Pulumi stack {stack_name!r}: {exc}") from exc

    deployment = _field(exported, "deployment")
    return deployment if deployment is not None else exported


def _select_deployed_resource(
    resource: BoundResource, deployment: Mapping[str, Any] | object
) -> Mapping[str, Any] | object:
    resources = _deployment_resources(deployment)
    candidates = [
        state
        for state in resources
        if _skaal_resource_id(state) == resource.inferred.id
        and _field(state, "type") not in {"pulumi:pulumi:Stack"}
    ]
    if not candidates:
        raise ValueError(
            f"Pulumi stack state does not contain a deployed resource tagged with "
            f"`skaal:resource_id={resource.inferred.id}`."
        )

    preferred = _AWS_TYPE_PREFERENCE.get(resource.inferred.kind, ())
    for resource_type in preferred:
        for state in candidates:
            if _field(state, "type") == resource_type:
                return state
    return candidates[0]


def _deployment_resources(deployment: Mapping[str, Any] | object) -> tuple[Mapping[str, Any] | object, ...]:
    resources = _field(deployment, "resources")
    if isinstance(resources, Sequence) and not isinstance(resources, (str, bytes, bytearray)):
        return tuple(resources)
    if isinstance(deployment, Mapping):
        nested = deployment.get("deployment")
        if nested is not None:
            return _deployment_resources(nested)
    nested = _field(deployment, "deployment")
    if nested is not None:
        return _deployment_resources(nested)
    return ()


def _skaal_resource_id(state: Mapping[str, Any] | object) -> str | None:
    for container_name in ("outputs", "inputProperties", "inputs"):
        container = _field(state, container_name)
        tags = _field(container, "tags")
        if isinstance(tags, Mapping):
            resource_id = tags.get("skaal:resource_id")
            if isinstance(resource_id, str):
                return resource_id
        tags_all = _field(container, "tagsAll")
        if isinstance(tags_all, Mapping):
            resource_id = tags_all.get("skaal:resource_id")
            if isinstance(resource_id, str):
                return resource_id
    return None


def _aws_console_url(state: Mapping[str, Any] | object, *, region: str | None) -> str:
    actual_region = region or "us-east-1"
    resource_type = str(_field(state, "type") or "")
    outputs = _field(state, "outputs")

    if resource_type == "aws:dynamodb/table:Table":
        name = _string_value(outputs, "name", "id")
        return (
            f"https://{actual_region}.console.aws.amazon.com/dynamodbv2/home"
            f"?region={actual_region}#table?name={quote(name)}"
        )
    if resource_type == "aws:s3/bucketV2:BucketV2":
        bucket = _string_value(outputs, "bucket", "id")
        return (
            "https://s3.console.aws.amazon.com/s3/buckets/"
            f"{quote(bucket)}?region={actual_region}&tab=objects"
        )
    if resource_type == "aws:rds/instance:Instance":
        identifier = _string_value(outputs, "identifier", "id")
        return (
            f"https://{actual_region}.console.aws.amazon.com/rds/home"
            f"?region={actual_region}#database:id={quote(identifier)};is-cluster=false"
        )
    if resource_type == "aws:elasticache/replicationGroup:ReplicationGroup":
        group = _string_value(outputs, "replicationGroupId", "id")
        return (
            f"https://{actual_region}.console.aws.amazon.com/elasticache/home"
            f"?region={actual_region}#/redis/{quote(group)}"
        )
    if resource_type == "aws:lambda/function:Function":
        name = _string_value(outputs, "name", "functionName", "id")
        return (
            f"https://{actual_region}.console.aws.amazon.com/lambda/home"
            f"?region={actual_region}#/functions/{quote(name)}"
        )
    if resource_type == "aws:apigatewayv2/api:Api":
        api_id = _string_value(outputs, "apiId", "id")
        return (
            f"https://{actual_region}.console.aws.amazon.com/apigateway/home"
            f"?region={actual_region}#/apis/{quote(api_id)}"
        )
    if resource_type == "aws:cloudwatch/eventRule:EventRule":
        name = _string_value(outputs, "name", "id")
        return (
            f"https://{actual_region}.console.aws.amazon.com/events/home"
            f"?region={actual_region}#/rules/{quote(name)}"
        )
    if resource_type == "aws:sqs/queue:Queue":
        queue_url = _string_value(outputs, "url", "id")
        return (
            f"https://{actual_region}.console.aws.amazon.com/sqs/v3/home"
            f"?region={actual_region}#/queues/{quote(queue_url, safe='')}"
        )
    if resource_type == "aws:secretsmanager/secret:Secret":
        name = _string_value(outputs, "name", "id")
        return (
            f"https://{actual_region}.console.aws.amazon.com/secretsmanager/secret"
            f"?region={actual_region}&name={quote(name)}"
        )
    msg = f"`skaal where` does not yet know how to open console URLs for {resource_type!r}."
    raise ValueError(msg)


def _physical_id(state: Mapping[str, Any] | object) -> str | None:
    outputs = _field(state, "outputs")
    for key in ("id", "name", "arn", "url"):
        value = _field(outputs, key)
        if isinstance(value, str) and value:
            return value
    value = _field(state, "id")
    return value if isinstance(value, str) and value else None


def _string_value(container: object, *keys: str) -> str:
    for key in keys:
        value = _field(container, key)
        if isinstance(value, str) and value:
            return value
    raise ValueError(f"Pulumi stack state is missing the expected fields: {', '.join(keys)}.")


def _field(container: object, key: str) -> Any:
    if isinstance(container, Mapping):
        return container.get(key)
    return getattr(container, key, None)


__all__ = ["WhereHit", "resolve_where"]
