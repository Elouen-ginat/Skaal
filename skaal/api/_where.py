"""Resolve deployed resources to cloud-console URLs."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, TypeAlias, cast
from urllib.parse import quote

from skaal.binding.model import BoundPlan, BoundResource, Environment, Target
from skaal.deploy import get_target
from skaal.errors import MissingExtraError, SkaalDeployError
from skaal.inference.model import ResourceKind

_DEFAULT_AWS_REGION = "us-east-1"
StackMapping: TypeAlias = Mapping[str, Any]
_AWS_RESOURCE_TYPE_PREFERENCE: dict[ResourceKind, tuple[str, ...]] = {
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


def _dynamodb_url(outputs: StackMapping, region: str) -> str:
    name = _string_value(outputs, "name", "id")
    return (
        f"https://{region}.console.aws.amazon.com/dynamodbv2/home"
        f"?region={region}#table?name={quote(name)}"
    )


def _s3_url(outputs: StackMapping, region: str) -> str:
    bucket = _string_value(outputs, "bucket", "id")
    return f"https://s3.console.aws.amazon.com/s3/buckets/{quote(bucket)}?region={region}&tab=objects"


def _rds_url(outputs: StackMapping, region: str) -> str:
    identifier = _string_value(outputs, "identifier", "id")
    return (
        f"https://{region}.console.aws.amazon.com/rds/home"
        f"?region={region}#database:id={quote(identifier)};is-cluster=false"
    )


def _elasticache_url(outputs: StackMapping, region: str) -> str:
    group = _string_value(outputs, "replicationGroupId", "id")
    return f"https://{region}.console.aws.amazon.com/elasticache/home?region={region}#/redis/{quote(group)}"


def _lambda_url(outputs: StackMapping, region: str) -> str:
    name = _string_value(outputs, "name", "functionName", "id")
    return f"https://{region}.console.aws.amazon.com/lambda/home?region={region}#/functions/{quote(name)}"


def _apigw_url(outputs: StackMapping, region: str) -> str:
    api_id = _string_value(outputs, "apiId", "id")
    return f"https://{region}.console.aws.amazon.com/apigateway/home?region={region}#/apis/{quote(api_id)}"


def _eventbridge_url(outputs: StackMapping, region: str) -> str:
    name = _string_value(outputs, "name", "id")
    return f"https://{region}.console.aws.amazon.com/events/home?region={region}#/rules/{quote(name)}"


def _sqs_url(outputs: StackMapping, region: str) -> str:
    queue_url = _string_value(outputs, "url", "id")
    return f"https://{region}.console.aws.amazon.com/sqs/v3/home?region={region}#/queues/{quote(queue_url, safe='')}"


def _secret_url(outputs: StackMapping, region: str) -> str:
    name = _string_value(outputs, "name", "id")
    return (
        f"https://{region}.console.aws.amazon.com/secretsmanager/secret"
        f"?region={region}&name={quote(name)}"
    )


_AWS_CONSOLE_URLS: dict[str, Callable[[StackMapping, str], str]] = {
    "aws:dynamodb/table:Table": _dynamodb_url,
    "aws:s3/bucketV2:BucketV2": _s3_url,
    "aws:rds/instance:Instance": _rds_url,
    "aws:elasticache/replicationGroup:ReplicationGroup": _elasticache_url,
    "aws:lambda/function:Function": _lambda_url,
    "aws:apigatewayv2/api:Api": _apigw_url,
    "aws:cloudwatch/eventRule:EventRule": _eventbridge_url,
    "aws:sqs/queue:Queue": _sqs_url,
    "aws:secretsmanager/secret:Secret": _secret_url,
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
            f"`skaal where` currently supports {Target.AWS.value!r} only; "
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
) -> StackMapping:
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

    deployment = _field(_coerce_mapping(exported), "deployment")
    return _coerce_mapping(deployment if deployment is not None else exported)


def _select_deployed_resource(resource: BoundResource, deployment: StackMapping) -> StackMapping:
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

    preferred = _AWS_RESOURCE_TYPE_PREFERENCE.get(resource.inferred.kind, ())
    for preferred_type in preferred:
        for state in candidates:
            if _field(state, "type") == preferred_type:
                return state
    return candidates[0]


def _deployment_resources(deployment: StackMapping) -> tuple[StackMapping, ...]:
    resources = _field(deployment, "resources")
    if isinstance(resources, (list, tuple)):
        return tuple(_coerce_mapping(resource) for resource in resources)
    nested = _field(deployment, "deployment")
    if nested is not None:
        return _deployment_resources(_coerce_mapping(nested))
    return ()


def _skaal_resource_id(state: StackMapping) -> str | None:
    for container_name in ("outputs", "inputProperties", "inputs"):
        resource_id = _tagged_resource_id(_coerce_mapping(_field(state, container_name)))
        if resource_id is not None:
            return resource_id
    return None


def _tagged_resource_id(container: StackMapping) -> str | None:
    for tag_field in ("tags", "tagsAll"):
        tags = _field(container, tag_field)
        if isinstance(tags, Mapping):
            resource_id = tags.get("skaal:resource_id")
            if isinstance(resource_id, str):
                return resource_id
    return None


def _aws_console_url(state: StackMapping, *, region: str | None) -> str:
    actual_region = region or _DEFAULT_AWS_REGION
    raw_resource_type = _field(state, "type")
    resource_type = str(raw_resource_type) if raw_resource_type is not None else ""
    outputs = _coerce_mapping(_field(state, "outputs"))
    resolver = _AWS_CONSOLE_URLS.get(resource_type)
    if resolver is not None:
        return resolver(outputs, actual_region)
    msg = f"`skaal where` does not support generating console URLs for {resource_type!r}."
    raise ValueError(msg)


def _physical_id(state: StackMapping) -> str | None:
    outputs = _coerce_mapping(_field(state, "outputs"))
    for key in ("id", "name", "arn", "url"):
        value = _field(outputs, key)
        if isinstance(value, str) and value:
            return value
    value = _field(state, "id")
    return value if isinstance(value, str) and value else None


def _string_value(container: StackMapping, *keys: str) -> str:
    for key in keys:
        value = _field(container, key)
        if isinstance(value, str) and value:
            return value
    raise ValueError(f"Pulumi stack state is missing the expected fields: {', '.join(keys)}.")


def _coerce_mapping(value: object) -> StackMapping:
    """Best-effort mapping view for Pulumi export values.

    Pulumi's export surface may hand back plain dicts or lightweight objects.
    Returning an empty dict for unsupported values keeps downstream lookups
    deterministic and lets the caller surface one domain-specific error rather
    than an attribute/type failure from the normalisation layer.
    """
    if isinstance(value, Mapping):
        return cast(StackMapping, value)
    if hasattr(value, "__dict__"):
        return cast(StackMapping, vars(value))
    return {}


def _field(container: StackMapping, key: str) -> Any:
    return container.get(key)


__all__ = ["WhereHit", "resolve_where"]
