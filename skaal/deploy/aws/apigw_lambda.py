"""APIGW + Lambda synth class — `aws.apigatewayv2.Api` fronting a Lambda image.

Used for `ASGI_SERVICE` resources (`app.mount(path, asgi_app)`).
Configuration tunables live in `AwsConfig.apigw` (route shape, stage) and
`AwsConfig.lambda_defaults.asgi_*` (timeout/memory ASGI overrides);
override either via ``[env.<name>.backends.aws.options.apigw]`` or
``[env.<name>.backends.aws.options.lambda_defaults]`` in `skaal.toml`.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pulumi
import pulumi_aws as aws

from skaal.backends.tokens import ApigwLambda
from skaal.deploy._protocol import SynthContext, SynthSpec, WherePreference, WhereSpec
from skaal.deploy.aws._config import AwsConfig
from skaal.deploy.aws._lambda import LambdaScaffold, LambdaSynth, PreScaffold
from skaal.deploy.aws._where import (
    AWS_APIGW_API,
    AWS_LAMBDA_FUNCTION,
    WHERE_FALLBACK,
    WHERE_PRIMARY,
    apigw_console_url,
    lambda_console_url,
)
from skaal.inference.model import ResourceKind


class ApigwLambdaSynth(LambdaSynth):
    """API Gateway HTTPv2 fronting a Lambda container."""

    SPEC: ClassVar[SynthSpec] = SynthSpec(
        tokens=(ApigwLambda,),
        description="API Gateway HTTPv2 fronting a Lambda container.",
        where=WhereSpec(
            preferences=(
                WherePreference(
                    kind=ResourceKind.ASGI_SERVICE,
                    provider_type=AWS_APIGW_API,
                    priority=WHERE_PRIMARY,
                ),
                WherePreference(
                    kind=ResourceKind.ASGI_SERVICE,
                    provider_type=AWS_LAMBDA_FUNCTION,
                    priority=WHERE_FALLBACK,
                ),
            ),
            console_url_resolvers={
                AWS_APIGW_API: apigw_console_url,
                AWS_LAMBDA_FUNCTION: lambda_console_url,
            },
        ),
    )

    def _timeout_s(self, ctx: SynthContext[AwsConfig]) -> int:
        overrides = ctx.resource.inferred.overrides
        if overrides.timeout_s:
            return int(overrides.timeout_s)
        return ctx.config.lambda_defaults.asgi_timeout_s

    def _memory_mb(self, ctx: SynthContext[AwsConfig]) -> int:
        overrides = ctx.resource.inferred.overrides
        return overrides.memory_mb or ctx.config.lambda_defaults.asgi_memory_mb

    def _event_source(
        self,
        ctx: SynthContext[AwsConfig],
        scaffold: LambdaScaffold,
        pre: PreScaffold,
    ) -> tuple[Any, ...]:
        cfg = ctx.config.apigw
        api = aws.apigatewayv2.Api(
            f"{ctx.pulumi_name}-api",
            protocol_type=cfg.protocol_type,
            tags=ctx.tags,
        )
        integration = aws.apigatewayv2.Integration(
            f"{ctx.pulumi_name}-integration",
            api_id=api.id,
            integration_type="AWS_PROXY",
            integration_uri=scaffold.function.invoke_arn,
            integration_method=cfg.integration_method,
            payload_format_version=cfg.payload_format_version,
        )
        route = aws.apigatewayv2.Route(
            f"{ctx.pulumi_name}-route",
            api_id=api.id,
            route_key=cfg.catch_all_route,
            target=pulumi.Output.concat("integrations/", integration.id),
        )
        stage = aws.apigatewayv2.Stage(
            f"{ctx.pulumi_name}-stage",
            api_id=api.id,
            name=cfg.stage_name,
            auto_deploy=cfg.auto_deploy,
            tags=ctx.tags,
        )
        permission = aws.lambda_.Permission(
            f"{ctx.pulumi_name}-perm",
            action="lambda:InvokeFunction",
            function=scaffold.function.name,
            principal="apigateway.amazonaws.com",
            source_arn=pulumi.Output.concat(api.execution_arn, "/*/*"),
        )
        return (api, integration, route, stage, permission)


__all__ = ["ApigwLambdaSynth"]
