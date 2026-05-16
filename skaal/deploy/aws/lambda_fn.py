"""Plain Lambda synth class — `aws.lambda_.Function` for `FUNCTION` resources.

Configuration tunables live in `AwsConfig.lambda_defaults`; override via
``[env.<name>.backends.aws.options.lambda_defaults]`` in `skaal.toml`.
Per-resource overrides (``ResourceOverrides.timeout_s`` /
``.memory_mb``) take precedence over the env-level defaults — handled
in `LambdaSynth._timeout_s` / `_memory_mb` on the base class.
"""

from __future__ import annotations

from typing import ClassVar

from skaal.deploy._protocol import SynthSpec, WherePreference, WhereSpec
from skaal.deploy.aws._lambda import LambdaSynth
from skaal.deploy.aws._where import AWS_LAMBDA_FUNCTION, WHERE_PRIMARY, lambda_console_url
from skaal.inference.model import ResourceKind


class PlainLambdaSynth(LambdaSynth):
    """Function-kind Lambda, invoked directly (no event source attached)."""

    SPEC: ClassVar[SynthSpec] = SynthSpec(
        backends=("lambda",),
        kinds=frozenset({ResourceKind.FUNCTION}),
        description="AWS Lambda function (image package).",
        where=WhereSpec(
            preferences=(
                WherePreference(
                    kind=ResourceKind.FUNCTION,
                    provider_type=AWS_LAMBDA_FUNCTION,
                    priority=WHERE_PRIMARY,
                ),
            ),
            console_url_resolvers={AWS_LAMBDA_FUNCTION: lambda_console_url},
        ),
    )


__all__ = ["PlainLambdaSynth"]
