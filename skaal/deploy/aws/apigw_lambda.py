"""APIGW + Lambda synth — `aws.apigatewayv2.Api` fronting a Lambda image.

Used for `ASGI_SERVICE` resources (`app.mount(path, asgi_app)`).
Configuration tunables live in `AwsConfig.apigw` (route shape, stage) and
`AwsConfig.lambda_defaults.asgi_*` (timeout/memory ASGI overrides);
override either via ``[env.<name>.backends.aws.options.apigw]`` or
``[env.<name>.backends.aws.options.lambda_defaults]`` in `skaal.toml`.
"""

from __future__ import annotations

import pulumi
import pulumi_aws as aws

from skaal.deploy._protocol import SynthContext, SynthResult, SynthSpec
from skaal.deploy.aws._config import AwsConfig
from skaal.deploy.aws._lambda_common import build_lambda
from skaal.inference.model import ResourceKind

SPEC = SynthSpec(
    backends=("apigw-lambda",),
    kinds=frozenset({ResourceKind.ASGI_SERVICE}),
    description="API Gateway HTTPv2 fronting a Lambda container.",
)


def synthesize(ctx: SynthContext[AwsConfig]) -> SynthResult:
    """Create an APIGW HTTP API fronting one container Lambda."""
    cfg = ctx.config
    overrides = ctx.resource.inferred.overrides
    scaffold = build_lambda(
        ctx,
        timeout=(
            int(overrides.timeout_s)
            if overrides.timeout_s
            else cfg.lambda_defaults.asgi_timeout_s
        ),
        memory_mb=overrides.memory_mb or cfg.lambda_defaults.asgi_memory_mb,
    )

    api = aws.apigatewayv2.Api(
        f"{ctx.pulumi_name}-api",
        protocol_type=cfg.apigw.protocol_type,
        tags=ctx.tags,
    )
    integration = aws.apigatewayv2.Integration(
        f"{ctx.pulumi_name}-integration",
        api_id=api.id,
        integration_type="AWS_PROXY",
        integration_uri=scaffold.function.invoke_arn,
        integration_method=cfg.apigw.integration_method,
        payload_format_version=cfg.apigw.payload_format_version,
    )
    route = aws.apigatewayv2.Route(
        f"{ctx.pulumi_name}-route",
        api_id=api.id,
        route_key=cfg.apigw.catch_all_route,
        target=pulumi.Output.concat("integrations/", integration.id),
    )
    stage = aws.apigatewayv2.Stage(
        f"{ctx.pulumi_name}-stage",
        api_id=api.id,
        name=cfg.apigw.stage_name,
        auto_deploy=cfg.apigw.auto_deploy,
        tags=ctx.tags,
    )
    permission = aws.lambda_.Permission(
        f"{ctx.pulumi_name}-perm",
        action="lambda:InvokeFunction",
        function=scaffold.function.name,
        principal="apigateway.amazonaws.com",
        source_arn=pulumi.Output.concat(api.execution_arn, "/*/*"),
    )

    return SynthResult(
        resource_id=ctx.resource_id,
        primary=scaffold.function,
        extras=(*scaffold.as_extras(), api, integration, route, stage, permission),
    )


__all__ = ["SPEC", "synthesize"]
