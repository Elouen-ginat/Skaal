"""Non-regression: deploy the kitchen-sink app to AWS.

Exercises every public decorator (KV + blob + relational storage, channel,
function with full resilience policies, job, two schedule kinds, sub-module
composition) on top of the AWS deploy path: Lambda + API Gateway + DynamoDB
+ RDS + S3 + EventBridge + SQS.
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest

from tests.nonregression.conftest import (
    deployed_stack,
    find_endpoint_url,
    requires_aws,
)

AWS_REGION_ENV = "AWS_REGION"
DEFAULT_AWS_REGION = "us-east-1"


def _skaal_toml(region: str) -> str:
    return f"""
[env.prod]
target = "aws"
region = "{region}"
""".lstrip()


def test_kitchen_sink_aws_deploy(tmp_path: Path) -> None:
    """Deploy the kitchen-sink app to AWS, hit the API, destroy, leak-check."""
    requires_aws()
    pytest.importorskip("pulumi", reason="`pulumi` automation API required.")
    pytest.importorskip("pulumi_aws", reason="`pulumi_aws` required for AWS resources.")

    region = os.environ.get(AWS_REGION_ENV, DEFAULT_AWS_REGION)
    with deployed_stack(
        tmp_path,
        example="nonregression_kitchen_sink",
        skaal_toml=_skaal_toml(region),
        env_name="prod",
        app_spec="app.app:app",
        target="aws",
        deploy_budget_seconds=900,
        aws_region=region,
    ) as stack:
        base_url = find_endpoint_url(stack.deploy_stdout, marker="execute-api")

        with httpx.Client(base_url=base_url, timeout=30.0) as client:
            healthz = client.get("/healthz")
            assert healthz.status_code == 200, (
                f"GET {base_url}/healthz returned {healthz.status_code}: {healthz.text}"
            )

            created = client.post(
                "/users",
                json={"id": "nonregression-aws-sink", "name": "kitchen sink"},
            )
            assert created.status_code == 201, (
                f"POST {base_url}/users returned {created.status_code}: {created.text}"
            )

            listed = client.get("/users")
            assert listed.status_code == 200, (
                f"GET {base_url}/users returned {listed.status_code}: {listed.text}"
            )
            ids = {u["id"] for u in listed.json().get("users", [])}
            assert "nonregression-aws-sink" in ids, (
                f"nonregression-aws-sink missing from /users response: {listed.json()}"
            )
