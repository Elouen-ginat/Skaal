"""Secrets Manager synth class — `aws.secretsmanager.Secret` per `SECRET` resource.

Configuration tunables live in `AwsConfig.secrets`; override via
``[env.<name>.backends.aws.options.secrets]`` in `skaal.toml`.
"""

from __future__ import annotations

from typing import ClassVar

import pulumi_aws as aws

from skaal.deploy._protocol import (
    SynthContext,
    SynthModule,
    SynthResult,
    SynthSpec,
    WherePreference,
    WhereSpec,
)
from skaal.deploy.aws._config import AwsConfig
from skaal.deploy.aws._where import (
    AWS_SECRETSMANAGER_SECRET,
    WHERE_PRIMARY,
    secret_console_url,
)
from skaal.inference.model import ResourceKind


class SecretsManagerSynth(SynthModule[AwsConfig]):
    """`aws.secretsmanager.Secret` containers (values supplied out-of-band)."""

    SPEC: ClassVar[SynthSpec] = SynthSpec(
        backends=("aws-secrets-manager",),
        kinds=frozenset({ResourceKind.SECRET}),
        description="AWS Secrets Manager container (value supplied out-of-band).",
        where=WhereSpec(
            preferences=(
                WherePreference(
                    kind=ResourceKind.SECRET,
                    provider_type=AWS_SECRETSMANAGER_SECRET,
                    priority=WHERE_PRIMARY,
                ),
            ),
            console_url_resolvers={AWS_SECRETSMANAGER_SECRET: secret_console_url},
        ),
    )

    def synthesize(self, ctx: SynthContext[AwsConfig]) -> SynthResult:
        cfg = ctx.config.secrets
        secret = aws.secretsmanager.Secret(ctx.pulumi_name, tags=ctx.tags)
        env_key = f"{cfg.env_var_prefix}{ctx.slug_key}{cfg.env_var_suffix}"
        return SynthResult(
            resource_id=ctx.resource_id,
            primary=secret,
            env_vars={env_key: secret.arn},
        )


__all__ = ["SecretsManagerSynth"]
