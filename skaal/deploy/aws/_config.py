"""Typed configuration for the AWS deploy target.

Every numeric / string default the AWS synth modules apply lives in one
of the pydantic models below. The aggregating `AwsConfig` exposes the
full tree, and `AwsConfig.from_env(env)` overlays values from
``env.backends["aws"].options`` in ``skaal.toml`` — that is the canonical
way for users to override defaults without touching `skaal/` source.

Example ``skaal.toml`` overlay:

```toml
[env.prod]
target = "aws"
region = "us-east-1"

[env.prod.backends.aws.options.lambda_defaults]
memory_mb = 1024
timeout_s = 60
log_retention_days = 30

[env.prod.backends.aws.options.postgres]
instance_class = "db.t3.medium"
allocated_storage_gb = 100

[env.prod.backends.aws.options.iam.policies]
dynamodb = "arn:aws:iam::123456789:policy/SkaalDynamoDBRestricted"
```

Synth modules read these fields off `ctx.config.<section>`; there are no
magic constants left in the synth code itself.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from pydantic import ConfigDict, Field

from skaal.deploy._protocol import TargetConfig

_LAMBDA_TRUST_POLICY = (
    '{"Version":"2012-10-17","Statement":[{"Action":"sts:AssumeRole",'
    '"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"}}]}'
)


_DEFAULT_POLICIES: Mapping[str, str] = {
    "dynamodb": "arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess",
    "s3": "arn:aws:iam::aws:policy/AmazonS3FullAccess",
    "postgres": "arn:aws:iam::aws:policy/AmazonRDSDataFullAccess",
    "redis": "arn:aws:iam::aws:policy/AmazonElastiCacheFullAccess",
    "redis-channel": "arn:aws:iam::aws:policy/AmazonElastiCacheFullAccess",
    "sqs": "arn:aws:iam::aws:policy/AmazonSQSFullAccess",
    "aws-secrets-manager": "arn:aws:iam::aws:policy/SecretsManagerReadWrite",
}


class IamConfig(TargetConfig):
    """IAM scaffold knobs for Lambda-shaped resources."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    lambda_trust_policy: str = _LAMBDA_TRUST_POLICY
    basic_execution_role_arn: str = (
        "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
    )
    policies: Mapping[str, str] = Field(default_factory=lambda: dict(_DEFAULT_POLICIES))


class EcrConfig(TargetConfig):
    """ECR repository knobs for the Lambda container image."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    force_delete: bool = True
    image_tag_mutability: Literal["MUTABLE", "IMMUTABLE"] = "MUTABLE"
    platform: str = "linux/amd64"


class LambdaConfig(TargetConfig):
    """Defaults for every Lambda-shaped resource (function / asgi / job / schedule)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    timeout_s: int = 30
    memory_mb: int = 512
    manage_log_group: bool = False
    log_retention_days: int = 14
    # Compute-kind-specific overrides; the synth picks the one matching its kind.
    asgi_timeout_s: int = 29
    asgi_memory_mb: int = 1024
    job_timeout_s: int = 60
    job_visibility_timeout_s: int = 120
    job_batch_size: int = 10


class DynamoDBConfig(TargetConfig):
    """Defaults for `aws.dynamodb.Table` resources."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    billing_mode: Literal["PAY_PER_REQUEST", "PROVISIONED"] = "PAY_PER_REQUEST"
    partition_key_name: str = "pk"
    partition_key_type: Literal["S", "N", "B"] = "S"
    env_var_prefix: str = "SKAAL_TABLE_"


class S3Config(TargetConfig):
    """Defaults for `aws.s3.BucketV2` resources."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sse_algorithm: Literal["AES256", "aws:kms"] = "AES256"
    env_var_prefix: str = "SKAAL_BUCKET_"


class SecretsConfig(TargetConfig):
    """Defaults for `aws.secretsmanager.Secret` resources."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    env_var_prefix: str = "SKAAL_SECRET_"
    env_var_suffix: str = "_ARN"


class PostgresConfig(TargetConfig):
    """Defaults for `aws.rds.Instance` Postgres resources."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    engine_version: str = "16"
    instance_class: str = "db.t3.micro"
    allocated_storage_gb: int = 20
    db_name: str = "skaal"
    username: str = "skaal"
    publicly_accessible: bool = False
    skip_final_snapshot: bool = True
    manage_master_user_password: bool = False
    env_var_prefix: str = "SKAAL_DB_"


class RedisConfig(TargetConfig):
    """Defaults for `aws.elasticache.ReplicationGroup` resources."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    engine_version: str = "7.1"
    node_type: str = "cache.t3.micro"
    num_cache_clusters: int = 1
    port: int = 6379
    transit_encryption: bool = True
    at_rest_encryption: bool = True
    automatic_failover: bool = False
    env_var_prefix: str = "SKAAL_REDIS_"
    env_var_suffix: str = "_URL"


class SqsConfig(TargetConfig):
    """Defaults for `aws.sqs.Queue` resources (channel form)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    visibility_timeout_s: int | None = None
    env_var_prefix: str = "SKAAL_CHANNEL_"
    env_var_suffix: str = "_URL"


class ApiGatewayConfig(TargetConfig):
    """Defaults for `aws.apigatewayv2.*` resources fronting ASGI Lambdas."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    protocol_type: Literal["HTTP", "WEBSOCKET"] = "HTTP"
    stage_name: str = "$default"
    auto_deploy: bool = True
    catch_all_route: str = "ANY /{proxy+}"
    payload_format_version: Literal["1.0", "2.0"] = "2.0"
    integration_method: str = "POST"


class EventBridgeConfig(TargetConfig):
    """Defaults for `aws.cloudwatch.EventRule` scheduled-Lambda resources."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fallback_schedule_expression: str = "rate(1 day)"


class AwsConfig(TargetConfig):
    """Aggregated AWS target config — every sub-config is overrideable via TOML.

    Constructed once per `Environment` via
    `AwsTarget.config_for(env) → AwsConfig.from_env(env)`; synth functions
    read fields off `ctx.config.<section>`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    iam: IamConfig = IamConfig()
    ecr: EcrConfig = EcrConfig()
    lambda_defaults: LambdaConfig = LambdaConfig()
    dynamodb: DynamoDBConfig = DynamoDBConfig()
    s3: S3Config = S3Config()
    secrets: SecretsConfig = SecretsConfig()
    postgres: PostgresConfig = PostgresConfig()
    redis: RedisConfig = RedisConfig()
    sqs: SqsConfig = SqsConfig()
    apigw: ApiGatewayConfig = ApiGatewayConfig()
    eventbridge: EventBridgeConfig = EventBridgeConfig()


__all__ = [
    "ApiGatewayConfig",
    "AwsConfig",
    "DynamoDBConfig",
    "EcrConfig",
    "EventBridgeConfig",
    "IamConfig",
    "LambdaConfig",
    "PostgresConfig",
    "RedisConfig",
    "S3Config",
    "SecretsConfig",
    "SqsConfig",
]
