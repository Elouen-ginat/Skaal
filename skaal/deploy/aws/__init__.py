"""AWS deploy target.

This package contributes one `DeployTarget` (`AwsTarget`) to the registry
at import time. Each synth module under this package declares its
`SPEC: SynthSpec` (which backends it serves, which kinds it handles) and
a `synthesize(ctx) -> SynthResult` function. The `_MODULES` tuple lists
every synth module — `AwsTarget.from_modules` walks it once and builds
the dispatch table.

**Adding a new AWS backend**: drop a new module in this package with
`SPEC` + `synthesize`, then add the module to `_MODULES`. No dict-literal
edit, no IAM-policy table edit (override in `AwsConfig.iam.policies` from
`skaal.toml`), no config-defaults edit (override in `AwsConfig.<section>`).
"""

from __future__ import annotations

from skaal.deploy._registry import register_target
from skaal.deploy.aws import (
    apigw_lambda,
    dynamodb,
    eventbridge,
    lambda_fn,
    postgres,
    redis,
    s3,
    secrets,
    sqs,
    sqs_worker,
)
from skaal.deploy.aws._config import AwsConfig
from skaal.deploy.aws._target import AwsTarget

_MODULES = (
    apigw_lambda,
    dynamodb,
    eventbridge,
    lambda_fn,
    postgres,
    redis,
    s3,
    secrets,
    sqs,
    sqs_worker,
)


TARGET = AwsTarget.from_modules(_MODULES)
register_target(TARGET)


__all__ = ["TARGET", "AwsConfig", "AwsTarget"]
