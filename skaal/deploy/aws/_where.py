"""AWS-specific `skaal where` metadata and console URL builders."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

from skaal.deploy._protocol import ConsoleUrlResolver

StackMapping = Mapping[str, Any]

AWS_DYNAMODB_TABLE = "aws:dynamodb/table:Table"
AWS_S3_BUCKET = "aws:s3/bucketV2:BucketV2"
AWS_RDS_INSTANCE = "aws:rds/instance:Instance"
AWS_ELASTICACHE_REPLICATION_GROUP = "aws:elasticache/replicationGroup:ReplicationGroup"
AWS_LAMBDA_FUNCTION = "aws:lambda/function:Function"
AWS_APIGW_API = "aws:apigatewayv2/api:Api"
AWS_EVENTBRIDGE_RULE = "aws:cloudwatch/eventRule:EventRule"
AWS_SQS_QUEUE = "aws:sqs/queue:Queue"
AWS_SECRETSMANAGER_SECRET = "aws:secretsmanager/secret:Secret"

WHERE_PRIMARY = 20
WHERE_FALLBACK = 10


def dynamodb_console_url(outputs: StackMapping, region: str | None) -> str:
    """Return the AWS console URL for a DynamoDB table export."""
    actual_region = _aws_region(region)
    name = _find_first_string_value(outputs, "name", "id")
    return (
        f"https://{actual_region}.console.aws.amazon.com/dynamodbv2/home"
        f"?region={actual_region}#table?name={quote(name)}"
    )


def s3_console_url(outputs: StackMapping, region: str | None) -> str:
    """Return the AWS console URL for an S3 bucket export."""
    actual_region = _aws_region(region)
    bucket = _find_first_string_value(outputs, "bucket", "id")
    return (
        f"https://s3.console.aws.amazon.com/s3/buckets/{quote(bucket)}"
        f"?region={actual_region}&tab=objects"
    )


def rds_console_url(outputs: StackMapping, region: str | None) -> str:
    """Return the AWS console URL for an RDS instance export."""
    actual_region = _aws_region(region)
    identifier = _find_first_string_value(outputs, "identifier", "id")
    return (
        f"https://{actual_region}.console.aws.amazon.com/rds/home"
        f"?region={actual_region}#database:id={quote(identifier)};is-cluster=false"
    )


def elasticache_console_url(outputs: StackMapping, region: str | None) -> str:
    """Return the AWS console URL for an ElastiCache replication group export."""
    actual_region = _aws_region(region)
    group = _find_first_string_value(outputs, "replicationGroupId", "id")
    return (
        f"https://{actual_region}.console.aws.amazon.com/elasticache/home"
        f"?region={actual_region}#/redis/{quote(group)}"
    )


def lambda_console_url(outputs: StackMapping, region: str | None) -> str:
    """Return the AWS console URL for a Lambda function export."""
    actual_region = _aws_region(region)
    name = _find_first_string_value(outputs, "name", "functionName", "id")
    return (
        f"https://{actual_region}.console.aws.amazon.com/lambda/home"
        f"?region={actual_region}#/functions/{quote(name)}"
    )


def apigw_console_url(outputs: StackMapping, region: str | None) -> str:
    """Return the AWS console URL for an API Gateway HTTP API export."""
    actual_region = _aws_region(region)
    api_id = _find_first_string_value(outputs, "apiId", "id")
    return (
        f"https://{actual_region}.console.aws.amazon.com/apigateway/home"
        f"?region={actual_region}#/apis/{quote(api_id)}"
    )


def eventbridge_console_url(outputs: StackMapping, region: str | None) -> str:
    """Return the AWS console URL for an EventBridge rule export."""
    actual_region = _aws_region(region)
    name = _find_first_string_value(outputs, "name", "id")
    return (
        f"https://{actual_region}.console.aws.amazon.com/events/home"
        f"?region={actual_region}#/rules/{quote(name)}"
    )


def sqs_console_url(outputs: StackMapping, region: str | None) -> str:
    """Return the AWS console URL for an SQS queue export."""
    actual_region = _aws_region(region)
    queue_url = _find_first_string_value(outputs, "url", "id")
    return (
        f"https://{actual_region}.console.aws.amazon.com/sqs/v3/home"
        f"?region={actual_region}#/queues/{quote(queue_url, safe='')}"
    )


def secret_console_url(outputs: StackMapping, region: str | None) -> str:
    """Return the AWS console URL for a Secrets Manager secret export."""
    actual_region = _aws_region(region)
    name = _find_first_string_value(outputs, "name", "id")
    return (
        f"https://{actual_region}.console.aws.amazon.com/secretsmanager/secret"
        f"?region={actual_region}&name={quote(name)}"
    )


def _aws_region(region: str | None) -> str:
    """Return a concrete AWS region for console URLs."""
    return region or "us-east-1"


def _find_first_string_value(container: StackMapping, *keys: str) -> str:
    for key in keys:
        value = container.get(key)
        if isinstance(value, str) and value:
            return value
    raise ValueError(f"Pulumi stack state is missing the expected fields: {', '.join(keys)}.")


AWS_CONSOLE_URLS: dict[str, ConsoleUrlResolver] = {
    AWS_DYNAMODB_TABLE: dynamodb_console_url,
    AWS_S3_BUCKET: s3_console_url,
    AWS_RDS_INSTANCE: rds_console_url,
    AWS_ELASTICACHE_REPLICATION_GROUP: elasticache_console_url,
    AWS_LAMBDA_FUNCTION: lambda_console_url,
    AWS_APIGW_API: apigw_console_url,
    AWS_EVENTBRIDGE_RULE: eventbridge_console_url,
    AWS_SQS_QUEUE: sqs_console_url,
    AWS_SECRETSMANAGER_SECRET: secret_console_url,
}


__all__ = [
    "AWS_APIGW_API",
    "AWS_CONSOLE_URLS",
    "AWS_DYNAMODB_TABLE",
    "AWS_ELASTICACHE_REPLICATION_GROUP",
    "AWS_EVENTBRIDGE_RULE",
    "AWS_LAMBDA_FUNCTION",
    "AWS_RDS_INSTANCE",
    "AWS_S3_BUCKET",
    "AWS_SECRETSMANAGER_SECRET",
    "AWS_SQS_QUEUE",
    "WHERE_FALLBACK",
    "WHERE_PRIMARY",
    "apigw_console_url",
    "dynamodb_console_url",
    "elasticache_console_url",
    "eventbridge_console_url",
    "lambda_console_url",
    "rds_console_url",
    "s3_console_url",
    "secret_console_url",
    "sqs_console_url",
]
