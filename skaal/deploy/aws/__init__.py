"""AWS deploy target.

This package contributes one `DeployTarget` (`AwsTarget`) to the registry
at import time. Each synth module under this package exports a single
`SynthModule` subclass that declares its `SPEC: ClassVar[SynthSpec]` and
implements `synthesize(ctx)`. `AwsTarget.from_classes(_SYNTHS)` walks the
tuple, instantiates each class, and assembles the dispatch table.

**Adding a new AWS backend**: drop a new module with a `SynthModule`
subclass, then add the class to `_SYNTHS`. Lambda-shaped backends should
inherit from `LambdaSynth` so they reuse the ECR + image + IAM + log
group + function scaffold; storage backends inherit directly from
`SynthModule[AwsConfig]`.

No backend-name → function dict literal is edited; no IAM-policy table
is edited (override `AwsConfig.iam.policies` via `skaal.toml`); no
config-defaults are edited (override `AwsConfig.<section>` via TOML).
"""

from __future__ import annotations

from skaal.deploy._protocol import SynthModule
from skaal.deploy._registry import register_target
from skaal.deploy.aws._config import AwsConfig
from skaal.deploy.aws._target import AwsTarget


def _load_synths() -> tuple[type[SynthModule[AwsConfig]], ...]:
    """Load AWS synths when optional Pulumi dependencies are available.

    Importing `skaal.deploy.aws` should stay safe for read-only code paths like
    `skaal where`, which only need the target identity and static metadata. When
    the Pulumi SDKs are missing we register an empty target here; build/deploy
    flows will still fail later when they need those extras.
    """
    try:
        from skaal.deploy.aws.apigw_lambda import ApigwLambdaSynth
        from skaal.deploy.aws.dynamodb import DynamoDBSynth
        from skaal.deploy.aws.eventbridge import EventBridgeLambdaSynth
        from skaal.deploy.aws.lambda_fn import PlainLambdaSynth
        from skaal.deploy.aws.postgres import PostgresSynth
        from skaal.deploy.aws.redis import RedisSynth
        from skaal.deploy.aws.s3 import S3Synth
        from skaal.deploy.aws.secrets import SecretsManagerSynth
        from skaal.deploy.aws.sqs import SqsChannelSynth
        from skaal.deploy.aws.sqs_worker import SqsWorkerSynth
    except ModuleNotFoundError as exc:
        if exc.name not in {"pulumi", "pulumi_aws", "pulumi_docker"}:
            raise
        return ()

    return (
        DynamoDBSynth,
        S3Synth,
        SecretsManagerSynth,
        PostgresSynth,
        RedisSynth,
        SqsChannelSynth,
        PlainLambdaSynth,
        ApigwLambdaSynth,
        EventBridgeLambdaSynth,
        SqsWorkerSynth,
    )


TARGET = AwsTarget.from_classes(_load_synths())
register_target(TARGET)


__all__ = ["TARGET", "AwsConfig", "AwsTarget"]
