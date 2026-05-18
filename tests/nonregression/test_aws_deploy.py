"""Non-regression: deploy `todo_api` against AWS, exercise the API, destroy.

This mirrors `tests/smoke/test_todo_api_aws.py` but is driven by the
non-regression gate (`SKAAL_NONREGRESSION_AWS` / `SKAAL_RUN_NONREGRESSION`)
and uses the shared `deployed_stack` lifecycle so the destroy step is
guaranteed to run even when an assertion fails mid-test.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from tests.nonregression.conftest import (
    deployed_stack,
    find_endpoint_url,
    requires_aws,
)

SKAAL_TOML = """
[env.prod]
target = "aws"
region = "us-east-1"
""".lstrip()


def test_todo_api_aws_deploy(tmp_path: Path) -> None:
    """Provision `examples/todo_api` against AWS Lambda + DynamoDB, then tear down."""
    requires_aws()
    pytest.importorskip("pulumi", reason="`pulumi` automation API required.")
    pytest.importorskip("pulumi_aws", reason="`pulumi_aws` required for AWS resources.")

    with deployed_stack(
        tmp_path,
        example="todo_api",
        skaal_toml=SKAAL_TOML,
        env_name="prod",
        app_spec="app.app:app",
        target="aws",
        deploy_budget_seconds=600,
    ) as stack:
        base_url = find_endpoint_url(stack.deploy_stdout, marker="execute-api")

        with httpx.Client(base_url=base_url, timeout=30.0) as client:
            created = client.post(
                "/todos",
                json={
                    "id": "nonregression-aws",
                    "title": "nonregression",
                    "description": "from CI",
                },
            )
            assert created.status_code == 201, created.text

            listed = client.get("/todos")
            assert listed.status_code == 200, listed.text
            ids = [t["id"] for t in listed.json().get("todos", [])]
            assert "nonregression-aws" in ids, (
                f"nonregression-aws missing from /todos response: {listed.json()}"
            )
