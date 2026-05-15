"""Structural tests for the AWS `DeployTarget`.

These tests guard the contract between the binding-layer defaults table
and the deploy-layer synth modules: every AWS-targetable backend must
have a synth registered, the dispatch must round-trip through the
`DeployTarget` protocol, and each synth module's `SPEC` must list
backends consistent with what the target reports.

`pulumi_aws` is imported eagerly by `skaal.deploy.aws.<module>` so the
test module itself requires the optional extra to load.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pulumi_aws")
pytest.importorskip("pulumi_docker")

from skaal.binding.model import Target
from skaal.binding.registry import REGISTRY
from skaal.deploy import DeployTarget, get_target
from skaal.deploy.aws import TARGET, AwsConfig, AwsTarget


def test_aws_target_satisfies_deploy_target_protocol() -> None:
    """`AwsTarget` is a runtime-checkable `DeployTarget`."""
    assert isinstance(TARGET, DeployTarget)
    assert isinstance(TARGET, AwsTarget)


def test_aws_target_registered_in_registry() -> None:
    """`skaal.deploy.aws` registers `TARGET` at import time."""
    assert get_target(Target.AWS) is TARGET


def test_aws_target_covers_every_aws_backend() -> None:
    """Every backend whose `targets` include `aws` has a synth entry."""
    aws_backends = {
        entry.token.name
        for entry in REGISTRY
        if Target.AWS in entry.targets
    }
    missing = aws_backends - TARGET.supported_backends()
    assert not missing, f"AWS backends without a synth module: {sorted(missing)}"


def test_aws_target_required_extras_match_sdks() -> None:
    """The target advertises the right importable modules."""
    assert TARGET.required_extras() == ("pulumi", "pulumi_aws", "pulumi_docker")


def test_aws_target_default_config_is_typed() -> None:
    """The default config round-trips through pydantic."""
    cfg = TARGET.default_config()
    assert isinstance(cfg, AwsConfig)
    assert cfg.lambda_defaults.memory_mb == 512


def test_aws_target_config_overlays_env_options() -> None:
    """TOML overrides on `env.backends["aws"].options` flow into the config."""
    from skaal.binding.model import BackendConfig, Environment

    env = Environment(
        name="prod",
        target=Target.AWS,
        region="us-east-1",
        backends={
            "aws": BackendConfig(
                options={
                    "lambda_defaults": {"memory_mb": 2048, "timeout_s": 60},
                    "postgres": {"instance_class": "db.t3.medium"},
                }
            )
        },
    )
    cfg = TARGET.config_for(env)
    assert isinstance(cfg, AwsConfig)
    assert cfg.lambda_defaults.memory_mb == 2048
    assert cfg.lambda_defaults.timeout_s == 60
    assert cfg.postgres.instance_class == "db.t3.medium"
    # Other fields keep their defaults
    assert cfg.dynamodb.partition_key_name == "pk"


def test_aws_target_stack_name_is_app_plus_env() -> None:
    """`stack_name` is `<app>-<env>`."""
    from skaal.binding.model import BoundPlan, Environment

    bound = BoundPlan(app="svc", environment="prod")
    env = Environment(name="prod", target=Target.AWS)
    assert TARGET.stack_name(bound, env) == "svc-prod"


def test_aws_target_stack_config_wires_region() -> None:
    """`stack_config` exposes `aws:region` when an env region is set."""
    from skaal.binding.model import Environment

    env = Environment(name="prod", target=Target.AWS, region="us-west-2")
    assert TARGET.stack_config(env) == {"aws:region": "us-west-2"}


def test_aws_target_lookup_returns_callable_or_none() -> None:
    for backend in TARGET.supported_backends():
        assert callable(TARGET.lookup_synth(backend))
    assert TARGET.lookup_synth("not-a-real-backend") is None


def test_aws_synth_classes_satisfy_the_module_contract() -> None:
    """Each synth class declares a `SPEC` class var and a `synthesize` method."""
    from skaal.deploy._protocol import SynthModule
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

    synth_classes = [
        ApigwLambdaSynth, DynamoDBSynth, EventBridgeLambdaSynth, PlainLambdaSynth,
        PostgresSynth, RedisSynth, S3Synth, SecretsManagerSynth, SqsChannelSynth,
        SqsWorkerSynth,
    ]
    for cls in synth_classes:
        assert issubclass(cls, SynthModule), f"{cls.__name__} not a SynthModule"
        assert hasattr(cls, "SPEC"), f"{cls.__name__} missing SPEC class var"
        assert cls.SPEC.backends, f"{cls.__name__} SPEC.backends is empty"
        assert cls.SPEC.kinds, f"{cls.__name__} SPEC.kinds is empty"
        assert callable(cls.synthesize), f"{cls.__name__} missing synthesize method"


def test_lambda_subclasses_share_the_base_scaffold() -> None:
    """The four Lambda-shaped synths inherit from `LambdaSynth`."""
    from skaal.deploy.aws._lambda import LambdaSynth
    from skaal.deploy.aws.apigw_lambda import ApigwLambdaSynth
    from skaal.deploy.aws.eventbridge import EventBridgeLambdaSynth
    from skaal.deploy.aws.lambda_fn import PlainLambdaSynth
    from skaal.deploy.aws.sqs_worker import SqsWorkerSynth

    for cls in (PlainLambdaSynth, ApigwLambdaSynth, EventBridgeLambdaSynth, SqsWorkerSynth):
        assert issubclass(cls, LambdaSynth), f"{cls.__name__} should inherit from LambdaSynth"
