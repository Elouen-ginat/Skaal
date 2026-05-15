"""APIGW + Lambda synth — `aws.apigatewayv2.Api` fronting one Lambda image.

Used for `ASGI_SERVICE` resources (`app.mount(path, asgi_app)`). The
Lambda inside is the same scaffold the plain ``lambda`` backend uses; the
extra plumbing is the HTTP API, a single proxy integration, a route per
mount path (Phase 4 emits one route covering the whole mount via
``ANY {proxy+}``), and the Lambda permission that lets API Gateway invoke
the function.
"""

from __future__ import annotations

import pulumi
import pulumi_aws as aws

from skaal.deploy.aws._context import SynthContext, SynthResult
from skaal.deploy.aws._lambda_common import build_lambda


def synthesize(ctx: SynthContext) -> SynthResult:
    """Create an APIGW HTTP API fronting one container Lambda."""
    overrides = ctx.resource.inferred.overrides
    scaffold = build_lambda(
        ctx,
        timeout=int(overrides.timeout_s) if overrides.timeout_s else 29,
        memory_mb=overrides.memory_mb or 1024,
    )

    api = aws.apigatewayv2.Api(
        f"{ctx.pulumi_name}-api",
        protocol_type="HTTP",
        tags=ctx.tags,
    )
    integration = aws.apigatewayv2.Integration(
        f"{ctx.pulumi_name}-integration",
        api_id=api.id,
        integration_type="AWS_PROXY",
        integration_uri=scaffold.function.invoke_arn,
        integration_method="POST",
        payload_format_version="2.0",
    )
    route = aws.apigatewayv2.Route(
        f"{ctx.pulumi_name}-route",
        api_id=api.id,
        route_key="ANY /{proxy+}",
        target=pulumi.Output.concat("integrations/", integration.id),
    )
    stage = aws.apigatewayv2.Stage(
        f"{ctx.pulumi_name}-stage",
        api_id=api.id,
        name="$default",
        auto_deploy=True,
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


__all__ = ["synthesize"]
